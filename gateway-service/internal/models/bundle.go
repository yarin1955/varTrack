package models

import (
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/models"
)

type Bundle struct {
	*pb.Bundle
}

func NewBundle(pbBundle *pb.Bundle) *Bundle {
	b := &Bundle{
		Bundle: pbBundle,
	}
	return b
}
