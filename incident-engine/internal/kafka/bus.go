// Package kafka wraps Redpanda/Kafka consume + produce for incident-engine.
package kafka

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/segmentio/kafka-go"
)

// Consumer reads JSON messages from a topic.
type Consumer struct {
	reader *kafka.Reader
}

// NewConsumer creates a consumer group reader.
func NewConsumer(brokers []string, topic, groupID string) *Consumer {
	return &Consumer{
		reader: kafka.NewReader(kafka.ReaderConfig{
			Brokers:        brokers,
			Topic:          topic,
			GroupID:        groupID,
			MinBytes:       1,
			MaxBytes:       10e6,
			CommitInterval: time.Second,
			StartOffset:    kafka.LastOffset,
		}),
	}
}

// Fetch reads the next message.
func (c *Consumer) Fetch(ctx context.Context) (kafka.Message, error) {
	return c.reader.FetchMessage(ctx)
}

// Commit commits a message.
func (c *Consumer) Commit(ctx context.Context, msg kafka.Message) error {
	return c.reader.CommitMessages(ctx, msg)
}

// Close closes the reader.
func (c *Consumer) Close() error {
	return c.reader.Close()
}

// Producer writes JSON values to a topic.
type Producer struct {
	writer *kafka.Writer
}

// NewProducer creates an async-capable writer.
func NewProducer(brokers []string, topic string) *Producer {
	return &Producer{
		writer: &kafka.Writer{
			Addr:                   kafka.TCP(brokers...),
			Topic:                  topic,
			Balancer:               &kafka.Hash{},
			RequiredAcks:           kafka.RequireOne,
			Async:                  false,
			AllowAutoTopicCreation: true,
		},
	}
}

// EnsureTopic creates topic if missing (idempotent).
func EnsureTopic(brokers []string, topic string) error {
	if len(brokers) == 0 || topic == "" {
		return fmt.Errorf("brokers/topic required")
	}
	conn, err := kafka.Dial("tcp", brokers[0])
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}
	defer conn.Close()
	controller, err := conn.Controller()
	if err != nil {
		return fmt.Errorf("controller: %w", err)
	}
	ctrl, err := kafka.Dial("tcp", fmt.Sprintf("%s:%d", controller.Host, controller.Port))
	if err != nil {
		return fmt.Errorf("dial controller: %w", err)
	}
	defer ctrl.Close()
	return ctrl.CreateTopics(kafka.TopicConfig{
		Topic:             topic,
		NumPartitions:     1,
		ReplicationFactor: 1,
	})
}

// Publish sends key/value bytes.
func (p *Producer) Publish(ctx context.Context, key, value []byte) error {
	err := p.writer.WriteMessages(ctx, kafka.Message{
		Key:   key,
		Value: value,
		Time:  time.Now().UTC(),
	})
	if err != nil {
		return fmt.Errorf("publish: %w", err)
	}
	return nil
}

// Close closes the writer.
func (p *Producer) Close() error {
	return p.writer.Close()
}

// RunLoop fetches messages until ctx is cancelled.
func RunLoop(ctx context.Context, c *Consumer, name string, handle func(context.Context, kafka.Message) error) {
	for {
		msg, err := c.Fetch(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			slog.Error("kafka_fetch_failed", "consumer", name, "err", err)
			time.Sleep(time.Second)
			continue
		}
		if err := handle(ctx, msg); err != nil {
			slog.Error("kafka_handle_failed", "consumer", name, "err", err)
			continue
		}
		if err := c.Commit(ctx, msg); err != nil {
			slog.Error("kafka_commit_failed", "consumer", name, "err", err)
		}
	}
}
