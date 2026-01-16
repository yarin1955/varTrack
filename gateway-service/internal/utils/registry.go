// gateway-service/internal/utils/registry.go
package utils

import (
	"fmt"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"reflect"
)

type PlatformConstructor func(p *pb.Platform) (IPlatform, error)

var (
	registry = make(map[string]PlatformConstructor)
	// Maps the oneof wrapper type (e.g. *pb.Platform_Github) to its name ("github")
	typeToName = make(map[reflect.Type]string)
)

// Register now takes an optional 'wrapper' to link the Go type to the name
func Register(name string, wrapper any, fn PlatformConstructor) {
	registry[name] = fn
	if wrapper != nil {
		typeToName[reflect.TypeOf(wrapper)] = name
	}
}

// ResolveKey returns the registered name for the active platform config
func ResolveKey(p *pb.Platform) string {
	if p == nil || p.GetConfig() == nil {
		return ""
	}
	// Direct map lookup by type
	return typeToName[reflect.TypeOf(p.GetConfig())]
}

func Create(p *pb.Platform) (IPlatform, error) {
	key := ResolveKey(p)
	fn, ok := registry[key]
	if !ok {
		return nil, fmt.Errorf("platform %s not registered", key)
	}

	return fn(p)
}
