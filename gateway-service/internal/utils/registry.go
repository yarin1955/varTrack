package utils

import (
	"fmt"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"path/filepath"
	"runtime"
	"strings"
)

type Factory[D any, T any] func(D) (T, error) // Changed: now returns (T, error)

type Registry[D any, T any] map[string]Factory[D, T]

func (r Registry[D, T]) Register(fn Factory[D, T]) {
	_, filename, _, ok := runtime.Caller(1)
	if !ok {
		return
	}

	base := filepath.Base(filename)
	name := strings.TrimSuffix(base, filepath.Ext(base))

	r[name] = fn
}

func (r Registry[D, T]) Create(name string, data D) (T, error) {
	fn, ok := r[name]
	if !ok {
		var zero T
		return zero, fmt.Errorf("factory for %s not found", name)
	}
	return fn(data) // Changed: fn now already returns (T, error)
}

var PlatformRegistry = make(Registry[*pb_models.Platform, IPlatform])

//
//import (
//	"fmt"
//	pb "gateway-service/internal/gen/proto/go/vartrack/v1/models"
//	"reflect"
//)
//
//type PlatformConstructor func(p *pb.Platform) (IPlatform, error)
//
//var (
//	registry = make(map[string]PlatformConstructor)
//	// Maps the oneof wrapper type (e.g. *pb.Platform_Github) to its name ("github")
//	typeToName = make(map[reflect.Type]string)
//)
//
//// Register now takes an optional 'wrapper' to link the Go type to the name
//func Register(name string, wrapper any, fn PlatformConstructor) {
//	registry[name] = fn
//	if wrapper != nil {
//		typeToName[reflect.TypeOf(wrapper)] = name
//	}
//}
//
//// ResolveKey returns the registered name for the active platform config
//func ResolveKey(p *pb.Platform) string {
//	if p == nil || p.GetConfig() == nil {
//		return ""
//	}
//	// Direct map lookup by type
//	return typeToName[reflect.TypeOf(p.GetConfig())]
//}
//
//func Create(p *pb.Platform) (IPlatform, error) {
//	key := ResolveKey(p)
//	fn, ok := registry[key]
//	if !ok {
//		return nil, fmt.Errorf("platform %s not registered", key)
//	}
//
//	return fn(p)
//}
