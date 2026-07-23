package cmd

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/argus-platform/argus/cli/internal/health"
	"github.com/spf13/cobra"
)

func newHealthCmd() *cobra.Command {
	c := &cobra.Command{
		Use:   "health",
		Short: "Ping local ARGUS services /health and print a status table",
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx, cancel := context.WithTimeout(cmd.Context(), 15*time.Second)
			defer cancel()
			results := health.Check(ctx, health.DefaultTargets(), nil)
			fmt.Fprint(os.Stdout, health.FormatTable(results))
			failed := 0
			for _, r := range results {
				if !r.OK {
					failed++
				}
			}
			if failed > 0 {
				return fmt.Errorf("%d service(s) unhealthy", failed)
			}
			return nil
		},
	}
	return c
}
