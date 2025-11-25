# from util.base_schema.git_platforms import BaseSettings
#
# class BitbucketConfig(base):
#     datasource: str  # e.g. "bitbucket"
#     api_url: str
#     workspace: str
#     token: str
#
#     def connect(self):
#         # your Bitbucket-specific connection logic
#         return f"Connecting to Bitbucket at {self.api_url}/workspace/{self.workspace}"