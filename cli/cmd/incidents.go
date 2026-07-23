package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/argus-platform/argus/cli/internal/gateway"
	"github.com/spf13/cobra"
)

func gatewayFlags(c *cobra.Command) {
	c.PersistentFlags().String("gateway-url", envOr("ARGUS_GATEWAY_URL", "http://localhost:8099"), "api-gateway base URL")
	c.PersistentFlags().String("api-key", envOr("ARGUS_API_KEY", "demo-operator"), "X-API-Key (demo-viewer|demo-operator|demo-admin)")
	c.PersistentFlags().String("token", os.Getenv("ARGUS_TOKEN"), "Bearer token (overrides api-key)")
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func newGatewayClient(cmd *cobra.Command) (*gateway.Client, error) {
	url, _ := cmd.Flags().GetString("gateway-url")
	key, _ := cmd.Flags().GetString("api-key")
	token, _ := cmd.Flags().GetString("token")
	return &gateway.Client{BaseURL: url, APIKey: key, Token: token}, nil
}

func newIncidentsCmd() *cobra.Command {
	c := &cobra.Command{
		Use:   "incidents",
		Short: "List and acknowledge incidents via api-gateway",
	}
	gatewayFlags(c)
	c.AddCommand(newIncidentsListCmd())
	c.AddCommand(newIncidentsAckCmd())
	return c
}

func newIncidentsListCmd() *cobra.Command {
	var status string
	var asJSON bool
	c := &cobra.Command{
		Use:   "list",
		Short: "List incidents",
		RunE: func(cmd *cobra.Command, args []string) error {
			client, err := newGatewayClient(cmd)
			if err != nil {
				return err
			}
			ctx, cancel := context.WithTimeout(cmd.Context(), 20*time.Second)
			defer cancel()
			items, err := client.ListIncidents(ctx, status)
			if err != nil {
				return err
			}
			if asJSON {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(items)
			}
			fmt.Printf("%-24s %-12s %-28s %s\n", "ID", "VEHICLE", "STATUS", "REASON")
			for _, i := range items {
				fmt.Printf("%-24s %-12s %-28s %s\n", i.IncidentID, i.VehicleID, i.Status, i.Reason)
			}
			return nil
		},
	}
	c.Flags().StringVar(&status, "status", "open", "Filter: open|acknowledged|resolved|\"\"")
	c.Flags().BoolVar(&asJSON, "json", false, "Print JSON")
	return c
}

func newIncidentsAckCmd() *cobra.Command {
	var note string
	c := &cobra.Command{
		Use:   "ack <incident-id>",
		Short: "Acknowledge an incident",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			client, err := newGatewayClient(cmd)
			if err != nil {
				return err
			}
			ctx, cancel := context.WithTimeout(cmd.Context(), 20*time.Second)
			defer cancel()
			inc, err := client.Acknowledge(ctx, args[0], note)
			if err != nil {
				return err
			}
			fmt.Printf("acked %s status=%s\n", inc.IncidentID, inc.Status)
			return nil
		},
	}
	c.Flags().StringVar(&note, "note", "acked via argusctl", "Ack note")
	return c
}
