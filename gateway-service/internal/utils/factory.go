package utils

import (
	"context"
	"fmt"
)

// DriverFactory is a generic factory that wraps a DriverRegistry.
type DriverFactory[D any, C any] struct {
	registry     *DriverRegistry[D, C]
	nameFunc     func(C) string
	validateFunc func(C) error
	typeName     string
}

func NewDriverFactory[D any, C any](
	registry *DriverRegistry[D, C],
	nameFunc func(C) string,
	validateFunc func(C) error,
	typeName string,
) *DriverFactory[D, C] {
	return &DriverFactory[D, C]{
		registry:     registry,
		nameFunc:     nameFunc,
		validateFunc: validateFunc,
		typeName:     typeName,
	}
}

func (f *DriverFactory[D, C]) Get(ctx context.Context, config C) (D, error) {
	var zero D

	if f.validateFunc != nil {
		if err := f.validateFunc(config); err != nil {
			return zero, err
		}
	}

	name := f.nameFunc(config)
	if name == "" {
		return zero, fmt.Errorf("%s: name must be specified", f.typeName)
	}

	return f.registry.Open(ctx, name, config)
}
