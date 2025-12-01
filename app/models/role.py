from pydantic import BaseModel, ConfigDict, model_validator, field_validator
from typing import List, Union, Optional, Dict
import re
import string

class RepositoryOverride(BaseModel):
    matchRepositories: Optional[List[str]] = None
    excludeRepositories: Optional[List[str]] = None

    model_config = ConfigDict(extra="allow")

class Role(BaseModel):
    platform: str
    datasource: str
    fileName: Optional[str] = None
    repositories: List[str]
    excludeRepositories: Optional[List[str]] = None
    envAsBranch: bool = False
    envAsPR: bool = False
    envAsTags: bool = False
    branchMap: Optional[Dict[str, str]] = None
    filePathMap: Optional[Dict[str, str]] = None
    uniqueKeyName: str = "{repoName}-{env}"
    variablesMap: Optional[Dict[str, str]] = None

    overrides: Optional[List[RepositoryOverride]] = None
    #prune: bool = False

    model_config = ConfigDict(
        extra="ignore",         # ignore unknown fields
        validate_default=True,  # validate defaults
    )

    @model_validator(mode='after')
    def validate_target_method(self) -> 'Role':
        """
        Validator 1: Ensure we know WHAT to scan.
        """
        if not self.fileName and not self.filePathMap:
            raise ValueError(
                "Configuration Error: You must provide either 'fileName' (for Branch strategies) "
                "or 'filePathMap' (for Directory strategies)."
            )
        return self

    @field_validator("filePathMap", "branchMap")
    @classmethod
    def validate_regex_patterns(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """
        Validator 2: Ensure maps use valid Regex patterns.
        """
        if not v:
            return v
        for pattern in v.keys():
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid Regex pattern '{pattern}': {e}")
        return v

    @field_validator("uniqueKeyName")
    @classmethod
    def validate_template_syntax(cls, v: str) -> str:
        """
        Validator 3: Syntax Check for the ID Template.
        Catches errors like '{repo-{env}' (missing closing brace).
        """
        try:
            # We don't care about values here, just syntax structure
            list(string.Formatter().parse(v))
        except ValueError as e:
            raise ValueError(f"Invalid format string syntax in uniqueKeyName: {e}")
        return v

    @model_validator(mode='after')
    def validate_template_logic(self) -> 'Role':
        """
        Validator 4: Logic Check (The most important one).
        Ensures that if the template needs '{env}', a strategy is actually enabled to provide it.
        """
        # A. Find what variables the template *needs*
        needed_vars = {
            fname for _, fname, _, _ in string.Formatter().parse(self.uniqueKeyName)
            if fname
        }

        # B. Define what variables are *always* available
        # Note: 'env' is NOT in this list yet!
        available_vars = {"repo", "repoName", "repositoryName", "branch", "file_path"}

        # C. Check if 'env' is provided by any strategy
        env_provided = (
                self.envAsBranch
                or self.envAsPR
                or self.envAsTags
                or (self.branchMap is not None)
                or (self.filePathMap is not None)
        )

        if env_provided:
            available_vars.add("env")

        # D. Check if regex groups in filePathMap provide extra variables (like {region})
        if self.filePathMap:
            for pattern in self.filePathMap.keys():
                if '(?P<' in pattern:
                    try:
                        regex = re.compile(pattern)
                        available_vars.update(regex.groupindex.keys())
                    except re.error:
                        pass

                        # E. Compare
        missing = needed_vars - available_vars
        if missing:
            raise ValueError(
                f"Configuration Error: 'uniqueKeyName' requires {missing}, but no strategy provides them. "
                f"If you use {{env}}, you must enable one of: envAsBranch, branchMap, or filePathMap."
            )

        return self

    # ==========================================
    #             HELPER METHODS
    # ==========================================

    def get_effective_config(self, repo_name: str) -> 'Role':
        """
        Merges overrides and re-validates the result.
        """
        final_config = self.model_dump(exclude={'overrides'})

        if not self.overrides:
            return self

        for rule in self.overrides:
            # Check Match
            if rule.matchRepositories:
                if not any(r in repo_name for r in rule.matchRepositories):
                    continue
                    # Check Exclude
            if rule.excludeRepositories:
                if any(r in repo_name for r in rule.excludeRepositories):
                    continue

            # Merge Data (allowing extra fields from overrides)
            updates = rule.model_dump(
                exclude={'matchRepositories', 'excludeRepositories'},
                exclude_unset=True
            )
            final_config.update(updates)

        # Re-Validation happens here
        return Role(**final_config)
