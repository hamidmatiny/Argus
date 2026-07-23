package cmd

import (
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/argus-platform/argus/cli/internal/secrets"
	"github.com/spf13/cobra"
)

func newSecretsCmd() *cobra.Command {
	c := &cobra.Command{
		Use:   "secrets",
		Short: "Manage provider credentials and env secrets",
	}
	c.AddCommand(newSecretsSetCmd())
	c.AddCommand(newSecretsDoctorCmd())
	return c
}

func newSecretsSetCmd() *cobra.Command {
	var fromStdin bool
	var skipValidate bool
	var skipRestart bool
	var repoRoot string

	c := &cobra.Command{
		Use:   "set [KEY=VALUE]",
		Short: "Set a secret in repo-root .env and reconcile duplicates",
		Long: `Write KEY=VALUE into the repository .env file (replacing any existing
line for that key), reconcile conflicting copies across the repo, live-validate
known provider keys, and restart only the compose services that consume it.

Examples:
  argusctl secrets set XAI_API_KEY="sk-abc123"
  echo 'XAI_API_KEY=sk-abc123' | argusctl secrets set --stdin
`,
		Args: cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			raw, err := readKV(args, fromStdin, cmd.InOrStdin())
			if err != nil {
				return err
			}
			key, value, err := secrets.ParseKV(raw)
			if err != nil {
				return err
			}
			opts := secrets.SetOptions{
				RepoRoot:     repoRoot,
				SkipValidate: skipValidate,
				SkipRestart:  skipRestart,
				Stdout:       cmd.OutOrStdout(),
				Stderr:       cmd.ErrOrStderr(),
			}
			res, err := secrets.Set(cmd.Context(), key, value, opts)
			if res != nil {
				secrets.PrintSetReport(cmd.OutOrStdout(), res)
			}
			return err
		},
	}
	c.Flags().BoolVar(&fromStdin, "stdin", false, "Read KEY=VALUE from stdin")
	c.Flags().BoolVar(&skipValidate, "skip-validate", false, "Skip live provider API validation")
	c.Flags().BoolVar(&skipRestart, "skip-restart", false, "Skip docker compose service restart")
	c.Flags().StringVar(&repoRoot, "repo-root", "", "Repository root (default: auto-detect)")
	return c
}

func newSecretsDoctorCmd() *cobra.Command {
	var repoRoot string
	var skipValidate bool
	c := &cobra.Command{
		Use:   "doctor",
		Short: "Audit env keys for missing defs, conflicts, and provider validity",
		RunE: func(cmd *cobra.Command, _ []string) error {
			rep, err := secrets.Doctor(cmd.Context(), secrets.DoctorOptions{
				RepoRoot:     repoRoot,
				SkipValidate: skipValidate,
			})
			if err != nil {
				return err
			}
			secrets.PrintDoctorReport(cmd.OutOrStdout(), rep)
			if !rep.OK() {
				return fmt.Errorf("secrets doctor found issues")
			}
			return nil
		},
	}
	c.Flags().StringVar(&repoRoot, "repo-root", "", "Repository root (default: auto-detect)")
	c.Flags().BoolVar(&skipValidate, "skip-validate", false, "Skip live provider API validation")
	return c
}

func readKV(args []string, fromStdin bool, in io.Reader) (string, error) {
	if fromStdin {
		b, err := io.ReadAll(in)
		if err != nil {
			return "", err
		}
		return strings.TrimSpace(string(b)), nil
	}
	if len(args) == 0 {
		return "", fmt.Errorf("expected KEY=VALUE argument (or --stdin)")
	}
	return args[0], nil
}

// Ensure os is referenced when tests import cmd with stdin from os.Stdin indirectly.
var _ = os.Stdin
