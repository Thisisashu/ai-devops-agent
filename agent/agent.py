import json
import ollama

from tools.aws import (
    get_aws_account,
    list_s3_buckets,
    list_ec2_instances
)

from tools.terraform import (
    terraform_fmt,
    terraform_init,
    terraform_validate,
    terraform_plan,
    write_terraform_file
)


MODEL = "qwen2.5:7b"


class DevOpsAgent:

    def __init__(self):

        self.messages = [
            {
                "role": "system",
                "content": """
You are an AI DevOps Agent.

You specialize in:

- AWS
- Terraform
- Linux
- Git
- CI/CD

You have access to AWS read-only tools and Terraform tools.

Rules:

1. Never invent AWS information.
2. Use AWS tools when the user asks for actual AWS information.
3. Never expose AWS credentials, access keys, secret keys, or sensitive information.
4. Never perform destructive AWS operations.
5. Terraform tools may generate, format, initialize, validate, and plan infrastructure.
6. Never run terraform apply automatically.
7. Always explain what you are doing.
8. Before making infrastructure changes, prefer terraform plan so the user can review the changes.
"""
            }
        ]

        self.tools = [

            # =========================================================
            # AWS TOOLS
            # =========================================================

            {
                "type": "function",
                "function": {
                    "name": "get_aws_account",
                    "description": (
                        "Get the AWS account identity information "
                        "for the currently authenticated AWS user."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },

            {
                "type": "function",
                "function": {
                    "name": "list_s3_buckets",
                    "description": (
                        "List all S3 buckets in the AWS account."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },

            {
                "type": "function",
                "function": {
                    "name": "list_ec2_instances",
                    "description": (
                        "List EC2 instances in the AWS account."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },

            # =========================================================
            # TERRAFORM TOOLS
            # =========================================================

            {
                "type": "function",
                "function": {
                    "name": "write_terraform_file",
                    "description": (
                        "Create or overwrite a Terraform file in the "
                        "terraform directory. Use this to generate "
                        "Terraform configuration."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": (
                                    "Terraform filename such as "
                                    "main.tf or variables.tf."
                                )
                            },
                            "content": {
                                "type": "string",
                                "description": (
                                    "Complete Terraform configuration "
                                    "to write into the file."
                                )
                            }
                        },
                        "required": [
                            "filename",
                            "content"
                        ]
                    }
                }
            },

            {
                "type": "function",
                "function": {
                    "name": "terraform_fmt",
                    "description": (
                        "Run terraform fmt to format Terraform "
                        "configuration files."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },

            {
                "type": "function",
                "function": {
                    "name": "terraform_init",
                    "description": (
                        "Run terraform init to initialize the "
                        "Terraform working directory."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },

            {
                "type": "function",
                "function": {
                    "name": "terraform_validate",
                    "description": (
                        "Run terraform validate to check whether "
                        "the Terraform configuration is valid."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },

            {
                "type": "function",
                "function": {
                    "name": "terraform_plan",
                    "description": (
                        "Run terraform plan to preview infrastructure "
                        "changes. This does not apply changes."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
        ]

    # =============================================================
    # TOOL EXECUTION
    # =============================================================

    def execute_tool(self, tool_name, arguments):

        # -------------------------
        # AWS
        # -------------------------

        if tool_name == "get_aws_account":

            return get_aws_account()

        elif tool_name == "list_s3_buckets":

            return list_s3_buckets()

        elif tool_name == "list_ec2_instances":

            return list_ec2_instances()

        # -------------------------
        # Terraform
        # -------------------------

        elif tool_name == "write_terraform_file":

            filename = arguments.get("filename")
            content = arguments.get("content")

            if not filename:
                return {
                    "error": "filename is required"
                }

            if not content:
                return {
                    "error": "content is required"
                }

            return write_terraform_file(
                filename,
                content
            )

        elif tool_name == "terraform_fmt":

            return terraform_fmt()

        elif tool_name == "terraform_init":

            return terraform_init()

        elif tool_name == "terraform_validate":

            return terraform_validate()

        elif tool_name == "terraform_plan":

            return terraform_plan()

        # -------------------------
        # Unknown tool
        # -------------------------

        else:

            return {
                "error": f"Unknown tool: {tool_name}"
            }

    # =============================================================
    # AGENT LOOP
    # =============================================================

    def run(self, user_message):

        self.messages.append({
            "role": "user",
            "content": user_message
        })

        while True:

            response = ollama.chat(
                model=MODEL,
                messages=self.messages,
                tools=self.tools
            )

            message = response["message"]

            # -----------------------------------------------------
            # No tool required
            # -----------------------------------------------------

            if not message.get("tool_calls"):

                answer = message.get(
                    "content",
                    ""
                )

                self.messages.append({
                    "role": "assistant",
                    "content": answer
                })

                return answer

            # -----------------------------------------------------
            # Tool call detected
            # -----------------------------------------------------

            self.messages.append(message)

            for tool_call in message["tool_calls"]:

                tool_name = tool_call["function"]["name"]

                arguments = tool_call["function"].get(
                    "arguments",
                    {}
                )

                print(
                    f"\n[Agent] Calling tool: {tool_name}"
                )

                print(
                    f"[Agent] Arguments: {arguments}"
                )

                try:

                    result = self.execute_tool(
                        tool_name,
                        arguments
                    )

                except Exception as e:

                    result = {
                        "error": str(e)
                    }

                print(
                    f"[Agent] Tool result: {result}"
                )

                self.messages.append({
                    "role": "tool",
                    "content": json.dumps(
                        result,
                        default=str
                    )
                })
