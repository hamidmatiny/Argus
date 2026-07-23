package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

// Root is the argusctl command tree.
var Root = &cobra.Command{
	Use:           "argusctl",
	Short:         "ARGUS operator CLI",
	SilenceUsage:  true,
	SilenceErrors: true,
}

// Execute runs the root command.
func Execute() error {
	if err := Root.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		return err
	}
	return nil
}

func init() {
	Root.AddCommand(newSecretsCmd())
}
