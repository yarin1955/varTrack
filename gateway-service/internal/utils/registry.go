package utils

import (
	"fmt"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/models"
)

type PlatformConstructor func(p *pb.Platform) (IPlatform, error)

var registry = make(map[string]PlatformConstructor)

func Register(name string, fn PlatformConstructor) {
	registry[name] = fn
}

func Create(p *pb.Platform) (IPlatform, error) {
	key := p.GetName()
	fn, ok := registry[key]
	if !ok {
		return nil, fmt.Errorf("platform %s not registered", key)
	}

	// Now calls the constructor and returns both the instance and the error
	return fn(p)
}
