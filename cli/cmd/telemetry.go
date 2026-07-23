package cmd

import (
	"errors"
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

func newTelemetryCmd() *cobra.Command {
	c := &cobra.Command{
		Use:   "telemetry",
		Short: "Telemetry helpers",
	}
	gatewayFlags(c)
	c.AddCommand(newTelemetryTailCmd())
	return c
}

func newTelemetryTailCmd() *cobra.Command {
	var vehicleID string
	var max int
	c := &cobra.Command{
		Use:   "tail",
		Short: "Stream live telemetry events from the gateway to the terminal",
		RunE: func(cmd *cobra.Command, args []string) error {
			client, err := newGatewayClient(cmd)
			if err != nil {
				return err
			}
			n := 0
			err = client.StreamTelemetry(cmd.Context(), vehicleID, func(line []byte) error {
				fmt.Fprintln(os.Stdout, string(line))
				n++
				if max > 0 && n >= max {
					return errTailStop
				}
				return nil
			})
			if errors.Is(err, errTailStop) {
				return nil
			}
			return err
		},
	}
	c.Flags().StringVar(&vehicleID, "vehicle-id", "", "Optional vehicle filter")
	c.Flags().IntVar(&max, "max", 0, "Stop after N events (0 = forever)")
	return c
}

var errTailStop = errors.New("tail stop")
