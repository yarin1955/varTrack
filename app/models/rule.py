from pydantic import BaseModel, ConfigDict, model_validator, field_validator
from typing import List, Union, Optional, Dict
import re
import string

from app.business_logic.dynamic_strategy import DynamicStrategySelector
from app.utils.enums.sync_mode import SyncMode

class RuleMatch(BaseModel):
    unique_key: str
    env: str

class RepositoryOverride(BaseModel):
    matchRepositories: Optional[List[str]] = None
    excludeRepositories: Optional[List[str]] = None
    enable: bool= False

    model_config = ConfigDict(extra="allow")

class Rule(BaseModel):
    platform: str
    datasource: str
    fileName: Optional[str] = None
    repositories: List[str]
    excludeRepositories: Optional[List[str]] = None
    envAsBranch: bool = False
    envAsPR: bool = False
    envAsTags: bool = False
    #value is destined env
    branchMap: Optional[Dict[str, str]] = None
    filePathMap: Optional[Dict[str, str]] = None
    uniqueKeyName: str = "{repoName}-{env}"
    variablesMap: Optional[Dict[str, str]] = None
    syncMode: SyncMode = SyncMode.GIT_SMART_REPAIR

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

    def resolve_rule_for_repo(self, repo_name: str) -> 'Role':
        if not self.overrides:
            return self

        final_config = self.model_dump(exclude={'overrides'})

        for override in self.overrides:
            if not override.enable:
                continue

            if override.matchRepositories:
                if not any(r in repo_name for r in override.matchRepositories):
                    continue
                    # Check Exclude
            if override.excludeRepositories:
                if any(r in repo_name for r in override.excludeRepositories):
                    continue

            updates = override.model_dump(
                exclude={'matchRepositories', 'excludeRepositories'},
                exclude_unset=True
            )
            final_config.update(updates)

            return Rule(**final_config)

    def resolve_sync_mode(self, sink, current_str):
        if self.syncMode != SyncMode.AUTO:
            return self.syncMode

        return DynamicStrategySelector.decide(content=current_str,sink=sink)

    def get_unique_key_and_env(self, file_path: str, branch: str) -> Optional[Dict[str, str]]:
        """
        Resolves the unique key and the environment variable.
        Priority:
        1. filePathMap (Directory/Regex strategy)
        2. fileName + branchMap (Branch strategy)
        """

        variables = self._build_base_variables(file_path, branch)
        env = None

        # Priority 1: Check filePathMap first (Per your request)
        # If this finds a match, it updates 'variables' with captured groups and returns env.
        if self.filePathMap:
            env = self._resolve_env_from_path(file_path, variables)

        # Priority 2: Fallback to Branch strategy if no env was found yet
        if env is None:
            # Only check branch strategy if fileName matches exactly
            if self.fileName and file_path == self.fileName:
                clean_branch = branch.replace('refs/heads/', '') if branch else ""
                env = self._resolve_env_from_branch(clean_branch)

        # Generate Key if env was resolved
        if env:
            variables["env"] = env
            key = self._format_unique_key(variables)
            return {"unique_key": key, "env": env}

        return None

    def get_unique_key(self, file_path: str, branch: str, repo_name: str) -> Optional[str]:

        variables = self._build_base_variables(file_path, branch, repo_name)

        # 2. Attempt to resolve environment using configured strategies
        env = self._resolve_environment(file_path, branch, variables)

        # 3. Generate final key if environment was resolved
        if env:
            variables["env"] = env
            return self._format_unique_key(variables)

        return None

    def resolve_keys_for_files(self, file_paths: List[str], branch: str, repo_name: str) -> Dict[str, str]:

        results = {}
        for file_path in file_paths:
            # Reuses the single-file logic we defined previously
            key = self.get_unique_key(file_path, branch, repo_name)

            if key:
                results[file_path] = key

        return results


    def _build_base_variables(self, file_path: str, branch: str) -> Dict[str, str]:
        """
        Constructs the base variable dictionary with standard metadata.

        Returns:
            Dictionary containing repo, repoName, branch, and file_path.
        """
        # Normalize branch name by removing refs prefix
        clean_branch = branch.replace('refs/heads/', '') if branch else ""

        # Extract short repo name (last segment after '/')

        variables = {
            "branch": clean_branch,
            "file_path": file_path
        }

        # Merge global variables (these can be overridden by strategy-specific values)
        if self.variablesMap:
            variables.update(self.variablesMap)

        return variables


    def _resolve_environment(
            self,
            file_path: str,
            branch: str,
            variables: Dict[str, str]
    ) -> Optional[str]:
        """
        Determines the environment value using configured strategies.
        Tries strategies in order: fileName match, filePathMap regex.

        Returns:
            The resolved environment string, or None if no strategy matched.
        """
        clean_branch = branch.replace('refs/heads/', '') if branch else ""

        # Strategy A: Exact fileName match (branch-based environment)
        if self.fileName and file_path == self.fileName:
            return self._resolve_env_from_branch(clean_branch)

        # Strategy B: filePathMap regex match (path-based environment)
        if self.filePathMap:
            return self._resolve_env_from_path(file_path, variables)

        return None


    def _resolve_env_from_branch(self, branch: str) -> Optional[str]:
        """
        Resolves environment from branch name using envAsBranch or branchMap.

        Returns:
            Environment string or None if no match.
        """
        # Direct branch-to-env mapping
        if self.envAsBranch:
            return branch

        # Regex-based branch mapping
        if self.branchMap:
            for pattern, env_val in self.branchMap.items():
                if re.match(pattern, branch):
                    return env_val

        return None

    def _resolve_env_from_path(
            self,
            file_path: str,
            variables: Dict[str, str]
    ) -> Optional[str]:
        """
        Resolves environment from file path using filePathMap regex patterns.
        """
        for pattern, map_value in self.filePathMap.items():
            match = re.match(pattern, file_path)
            if not match:
                continue

            # Create a context specific to this match to avoid polluting
            # the main 'variables' dict if we continue the loop
            context_variables = variables.copy()

            # Extract and merge any named capture groups
            captured_groups = match.groupdict()
            context_variables.update(captured_groups)

            # Determine environment using the specific context
            env = self._interpret_map_value(map_value, context_variables, captured_groups)

            if env:
                # Only NOW do we update the main variables dict with the winner's data
                variables.update(captured_groups)
                return env

        return None


    def _interpret_map_value(
            self,
            map_value: str,
            variables: Dict[str, str],
            captured_groups: Dict[str, str]
    ) -> Optional[str]:
        """
        Interprets a filePathMap value, which can be:
        - A template string like "{region}" or "{env}"
        - A literal string like "production"

        Returns:
            The resolved environment value or None.
        """
        # Case 1: Template string requiring interpolation
        if "{" in map_value:
            try:
                return map_value.format(**variables)
            except KeyError as e:
                # Template references undefined variable
                print(f"⚠️ [Template Error] Cannot resolve '{map_value}': missing variable {e}")
                return None

        # Case 2: Literal environment value
        if map_value:
            return map_value

        # Case 3: Fallback to captured 'env' group if map_value is empty
        return captured_groups.get("env")


    def _format_unique_key(self, variables: Dict[str, str]) -> Optional[str]:
        """
        Formats the uniqueKeyName template using resolved variables.

        Returns:
            The formatted key string or None if formatting fails.
        """
        try:
            return self.uniqueKeyName.format(**variables)
        except KeyError as e:
            print(
                f"⚠️ [Key Generation Error] Template '{self.uniqueKeyName}' "
                f"requires missing variable: {e}"
            )
            return None
