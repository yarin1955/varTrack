package config

import (
	"fmt"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"gateway-service/internal/models"
	"google.golang.org/protobuf/encoding/protojson"

	"cuelang.org/go/cue"
	"cuelang.org/go/cue/cuecontext"
	"cuelang.org/go/cue/load"

	_ "gateway-service/internal/models/platforms"
)

func NewBundle(cuePath string) (*models.Bundle, error) {
	bundle, err := loadBundleFromCueFile(cuePath)
	if err != nil {
		return nil, fmt.Errorf("failed to load bundle from CUE: %w", err)
	}

	return models.NewBundle(bundle), nil
}


func loadBundleFromCueFile(cuePath string) (*pb_models.Bundle, error) {
	// Create load config
	cfg := &load.Config{}

	// Load CUE files
	buildInstances := load.Instances([]string{cuePath}, cfg)
	if len(buildInstances) == 0 {
		return nil, fmt.Errorf("no CUE instances found")
	}

	if buildInstances[0].Err != nil {
		return nil, fmt.Errorf("failed to load CUE files: %w", buildInstances[0].Err)
	}

	// Get CUE context
	ctx := cuecontext.New()

	// Build the instance
	value := ctx.BuildInstance(buildInstances[0])
	if value.Err() != nil {
		return nil, fmt.Errorf("failed to build CUE: %w", value.Err())
	}

	// Look up the bundle field
	bundleValue := value.LookupPath(cue.ParsePath("bundle"))
	if bundleValue.Err() != nil {
		return nil, fmt.Errorf("bundle not found in CUE: %w", bundleValue.Err())
	}

	// Validate the bundle
	if err := bundleValue.Validate(cue.Concrete(true)); err != nil {
		return nil, fmt.Errorf("bundle validation failed: %w", err)
	}

	// Convert to JSON
	jsonBytes, err := bundleValue.MarshalJSON()
	if err != nil {
		return nil, fmt.Errorf("failed to marshal bundle to JSON: %w", err)
	}

	// Unmarshal into protobuf
	bundle := &pb_models.Bundle{}
	if err := protojson.Unmarshal(jsonBytes, bundle); err != nil {
		return nil, fmt.Errorf("failed to unmarshal into protobuf: %w", err)
	}

	return bundle, nil
}

// ... existing LoadFromCue and ValidateBundle functions ...

//// gateway-service/internal/config/loader.go
//package config
//
//import (
//	"fmt"
//	"log/slog"
//
//	models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
//
//	"buf.build/go/protovalidate"
//	"cuelang.org/go/cue/cuecontext"
//	"cuelang.org/go/cue/load"
//)
//
//func LoadFromCue(cueEntrypoint string) (*models.Bundle, error) {
//	ctx := cuecontext.New()
//
//	slog.Debug("starting configuration load", "path", cueEntrypoint)
//
//	bis := load.Instances([]string{cueEntrypoint}, &load.Config{})
//	if len(bis) == 0 {
//		err := fmt.Errorf("no CUE instances found")
//		slog.Error("failed to find CUE instances", "path", cueEntrypoint, "error", err)
//		return nil, err
//	}
//
//	value := ctx.BuildInstance(bis[0])
//	if value.Err() != nil {
//		err := fmt.Errorf("cue build error: %v", value.Err())
//		slog.Error("failed to build CUE instance", "error", err)
//		return nil, err
//	}
//
//	var bundle models.Bundle
//	err := value.Decode(&bundle)
//	if err != nil {
//		err := fmt.Errorf("failed to decode CUE: %v", err)
//		slog.Error("failed to decode CUE into bundle", "error", err)
//		return nil, err
//	}
//
//	slog.Info("CUE decoded successfully, starting validation")
//
//	err = ValidateBundle(&bundle)
//	if err != nil {
//		slog.Error("bundle validation failed", "error", err)
//		return nil, fmt.Errorf("bundle validation failed: %w", err)
//	}
//
//	slog.Info("configuration bundle loaded and validated successfully")
//	return &bundle, nil
//}
//
//func ValidateBundle(bundle *models.Bundle) error {
//	slog.Debug("initializing protovalidate validator")
//
//	// 1. Initialize the validator
//	v, err := protovalidate.New()
//	if err != nil {
//		return fmt.Errorf("failed to initialize protovalidate: %w", err)
//	}
//
//	// 2. Perform the validation
//	// This recursively checks the Bundle and all nested messages (Rules, Platforms, etc.)
//	if err := v.Validate(bundle); err != nil {
//		slog.Error("validation failed", "error", err)
//		return err
//	}
//
//	slog.Debug("bundle validation passed")
//	return nil
//}


// type Loader struct {
// 	cuePath string
// 	bundle  *models.Bundle
// 	mu      sync.RWMutex
// }

// func NewLoader(cuePath string) *Loader {
// 	return &Loader{
// 		cuePath: cuePath,
// 	}
// }

// func (l *Loader) GetPlatformConfig(platformName string) (*pb_models.Platform, error) {
// 	l.mu.Lock()
// 	if l.bundle == nil {
// 		// --- RAW CUE LOADING LOGIC ---
// 		ctx := cuecontext.New()
// 		bis := load.Instances([]string{l.cuePath}, nil)
// 		if len(bis) == 0 {
// 			l.mu.Unlock()
// 			return nil, fmt.Errorf("no CUE instances found at %s", l.cuePath)
// 		}

// 		v := ctx.BuildInstance(bis[0])
// 		if v.Err() != nil {
// 			l.mu.Unlock()
// 			return nil, fmt.Errorf("failed to build CUE instance: %v", v.Err())
// 		}

// 		// Decode directly into the raw Protobuf struct
// 		pbBundle := &pb_models.Bundle{}
// 		if err := v.Decode(pbBundle); err != nil {
// 			l.mu.Unlock()
// 			return nil, fmt.Errorf("failed to decode CUE into Protobuf: %v", err)
// 		}

// 		l.bundle = models.NewBundle(pbBundle)
// 	}
// 	l.mu.Unlock()

// 	l.mu.RLock()
// 	defer l.mu.RUnlock()

// 	// Inline platform search

// 	for _, p := range l.bundle.Platforms {
// 		fmt.Printf("Checking platform in CUE. Has Github: %v\n", p.GetGithub() != nil)
// 		if platformName == "github" && p.GetGithub() != nil {
// 			return p, nil
// 		}
// 	}

// 	return nil, fmt.Errorf("platform %s not found in CUE bundle", platformName)
// }