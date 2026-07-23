package cmd

import (
	"context"
	"fmt"
	"time"

	"github.com/spf13/cobra"
)

func newRetrainCmd() *cobra.Command {
	c := &cobra.Command{
		Use:   "retrain",
		Short: "Trigger model retraining via api-gateway → Dagster",
	}
	gatewayFlags(c)
	c.AddCommand(newRetrainTriggerCmd())
	return c
}

func newRetrainTriggerCmd() *cobra.Command {
	var reason string
	c := &cobra.Command{
		Use:   "trigger",
		Short: "POST /v1/retraining:trigger",
		RunE: func(cmd *cobra.Command, args []string) error {
			client, err := newGatewayClient(cmd)
			if err != nil {
				return err
			}
			ctx, cancel := context.WithTimeout(cmd.Context(), 60*time.Second)
			defer cancel()
			out, err := client.TriggerRetrain(ctx, reason)
			if err != nil {
				return err
			}
			fmt.Printf("run_id=%s status=%s message=%s\n", out.RunID, out.Status, out.Message)
			return nil
		},
	}
	c.Flags().StringVar(&reason, "reason", "argusctl", "Retrain reason")
	return c
}
