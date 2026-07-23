package main

import (
	"os"

	"github.com/argus-platform/argus/cli/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
