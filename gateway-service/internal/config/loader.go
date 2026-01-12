// gateway-service/internal/config/loader.go
package config

import (
	"fmt"
	"log/slog"

	models "gateway-service/internal/gen/proto/go/vartrack/v1/models"

	"buf.build/go/protovalidate"
	"cuelang.org/go/cue/cuecontext"
	"cuelang.org/go/cue/load"
)

func LoadFromCue(cueEntrypoint string) (*models.Bundle, error) {
	ctx := cuecontext.New()

	slog.Debug("starting configuration load", "path", cueEntrypoint)

	bis := load.Instances([]string{cueEntrypoint}, &load.Config{})
	if len(bis) == 0 {
		err := fmt.Errorf("no CUE instances found")
		slog.Error("failed to find CUE instances", "path", cueEntrypoint, "error", err)
		return nil, err
	}

	value := ctx.BuildInstance(bis[0])
	if value.Err() != nil {
		err := fmt.Errorf("cue build error: %v", value.Err())
		slog.Error("failed to build CUE instance", "error", err)
		return nil, err
	}

	var bundle models.Bundle
	err := value.Decode(&bundle)
	if err != nil {
		err := fmt.Errorf("failed to decode CUE: %v", err)
		slog.Error("failed to decode CUE into bundle", "error", err)
		return nil, err
	}

	slog.Info("CUE decoded successfully, starting validation")

	err = ValidateBundle(&bundle)
	if err != nil {
		slog.Error("bundle validation failed", "error", err)
		return nil, fmt.Errorf("bundle validation failed: %w", err)
	}

	slog.Info("configuration bundle loaded and validated successfully")
	return &bundle, nil
}

func ValidateBundle(bundle *models.Bundle) error {
	slog.Debug("initializing protovalidate validator")

	// 1. Initialize the validator
	v, err := protovalidate.New()
	if err != nil {
		return fmt.Errorf("failed to initialize protovalidate: %w", err)
	}

	// 2. Perform the validation
	// This recursively checks the Bundle and all nested messages (Rules, Platforms, etc.)
	if err := v.Validate(bundle); err != nil {
		slog.Error("validation failed", "error", err)
		return err
	}

	slog.Debug("bundle validation passed")
	return nil
}
