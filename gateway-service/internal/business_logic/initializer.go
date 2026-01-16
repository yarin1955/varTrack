package business_logic

import (
	"fmt"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"gateway-service/internal/models"
	"gateway-service/internal/utils"
	"net/url"
)

func Initialize(pbBundle *pb.Bundle) error {

	bundle := models.NewBundle(pbBundle)
	for _, pbRule := range bundle.GetRules() {
		// rule is now your custom wrapper type
		rule := &models.Rule{Rule: pbRule}

		// 1. Find the platform config that matches the rule's platform name
		pbPlatform := bundle.GetPlatformByName(rule.GetPlatform())
		if pbPlatform == nil {
			return fmt.Errorf("platform %s not found in bundle for rule %s", rule.GetPlatform(), rule.GetDatasource())
		}

		// 2. Create the platform instance using the registry
		p, err := utils.Create(pbPlatform)
		if err != nil {
			return fmt.Errorf("failed to create platform driver: %w", err)
		}

		// 3. Discover and filter repositories
		repos, err := ResolveRuleRepositories(rule, p)
		if err != nil {
			return fmt.Errorf("failed to resolve repositories: %w", err)
		}

		for _, repo := range repos {
			path, _ := url.JoinPath("/", rule.GetPlatform(), rule.GetDatasource())
			err := p.CreateWebhook(repo, path)
			if err != nil {
				// Handle the error (log it, return it, etc.)
				fmt.Printf("failed to create webhook: %v\n", err)
				return err
			}
		}

		p.Close()
	}

	return nil

}
