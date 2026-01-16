package models

import (
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"gateway-service/internal/utils"
)

type Platform struct {
	pb       *pb.Platform
	instance utils.IPlatform // Store the implementation instance
}

func (p *Platform) GetSecret() string {
	if p.instance == nil {
		return ""
	}
	return p.instance.GetSecret()
}

func (p *Platform) GetGitScmSignature() string {
	if p.instance == nil {
		return ""
	}
	return p.instance.GetGitScmSignature()
}
