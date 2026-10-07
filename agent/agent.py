import json
import os
from pathlib import Path

import ollama

from tools.aws import (
    get_aws_account,
    list_s3_buckets,
    list_ec2_instances,
)

from tools.terraform import (
    terraform_fmt,
    terraform_init,
    terraform_validate,
    terraform_plan,
    write_terraform_file,
)

MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
TERRAFORM_DIR = Path(__file__).resolve().parent.parent / "terraform"


SYSTEM_PROMPT = f"""
You are an AI DevOps Agent responsible for managing infrastructure through
Terraform.

Terraform directory:
{TERRAFORM_DIR}

============================================================
EXECUTION POLICY
============================================================

When the user gives an explicit executable request:

1. Execute the request immediately.
2. Do NOT ask for confirmation.
3. Do NOT ask:
   - "Would you like me to proceed?"
   - "Should I continue?"
   - "Do you want me to run this?"
   - "Shall I proceed?"
4. Do not stop after explaining what you intend to do.
5. Actually call the available tools.
6. Continue through the required workflow until the task is complete or
   an actual tool limitation prevents completion.
7. Only ask the user a question if a required value genuinely cannot
   be discovered with the available tools.

The user saying:
"Do not ask me what to do next"
means you MUST continue execution automatically.


============================================================
AWS SAFETY
============================================================

1. Never invent AWS information.

2. Never invent:
   - AMI IDs
   - VPC IDs
   - subnet IDs
   - security-group IDs
   - key-pair names
   - instance IDs
   - bucket names
   - account IDs

3. If the user requests dynamic discovery, use AWS read-only tools.

4. Never expose:
   - AWS access keys
   - AWS secret keys
   - session tokens
   - credentials

5. Never create AWS access keys.

6. Never create SSH access from 0.0.0.0/0 unless the user explicitly
   requests it.

7. Never destroy or modify unrelated AWS infrastructure.

8. Never claim an AWS resource was created unless an actual Terraform
   apply/deployment result confirms it.


============================================================
TERRAFORM SAFETY
============================================================

1. Preserve existing Terraform resources.

2. Never replace main.tf with only a newly requested resource.

3. New independent resources should normally be created in a separate
   Terraform file.

4. Preserve the existing remote S3 backend.

5. Do not modify backend.tf unless explicitly requested.

6. Do not modify existing resources unless the user explicitly requests
   that modification.

7. Do not introduce undeclared Terraform variables.

8. Never invent placeholder values such as:
   - var.random_suffix
   - my-second-bucket
   - my-key-pair
   - example AMI IDs

9. Use the exact values supplied by the user.

10. If the user requests a resource to be dynamically discovered, discover
    it first rather than asking the user for the value.


============================================================
TERRAFORM WORKFLOW
============================================================

For Terraform infrastructure changes:

1. Inspect the existing Terraform configuration.

2. Preserve existing resources.

3. Create the requested new Terraform configuration.

4. Run:

   terraform fmt

5. Run:

   terraform init -reconfigure

6. Run:

   terraform validate

7. If validation fails:
   - diagnose the error
   - fix the Terraform configuration
   - rerun terraform fmt
   - rerun terraform init -reconfigure
   - rerun terraform validate

8. Run:

   terraform plan -input=false

9. Inspect the actual plan.

10. If the user specified an expected plan such as:

    Plan: 1 to add, 0 to change, 0 to destroy

    verify that the actual plan satisfies it.

11. Never claim "No changes" unless the actual Terraform plan says
    "No changes."

12. Never run terraform apply locally.


============================================================
GIT
============================================================

Only perform Git commit/push when the user explicitly requests it.

Never claim:
- commit completed
- push completed

unless an actual Git tool/command performed the operation.


============================================================
GITHUB ACTIONS
============================================================

When the user requires deployment through GitHub Actions:

1. Terraform apply must NOT happen locally.

2. The expected workflow is:

   Terraform plan
        |
        v
   GitHub Actions
        |
        v
   production environment
        |
        v
   manual approval
        |
        v
   terraform apply

3. Never bypass production environment protection.

4. Never claim manual approval occurred unless an actual workflow result
   confirms it.

5. Never claim deployment completed unless an actual GitHub Actions
   deployment result confirms it.


============================================================
HONESTY
============================================================

Never fabricate:

- tool calls
- AWS results
- Terraform output
- Git commits
- Git pushes
- GitHub Actions results
- production approvals
- infrastructure deployments

If a required operation cannot be performed because the required tool
does not exist, clearly report that limitation.


============================================================
IMPORTANT
============================================================

If the user explicitly says:

"Execute the task"

then execute the task.

Do not respond with a plan asking for confirmation.

Do not ask the user what to do next.
"""


class DevOpsAgent:

    def __init__(self):

        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        self.tools = [

            # ============================================================
            # AWS
            # ============================================================

            {
                "type": "function",
                "function": {
                    "name": "get_aws_account",
                    "description": (
                        "READ-ONLY. Get the AWS account identity of the "
                        "currently authenticated AWS identity."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },

            {
                "type": "function",
                "function": {
                    "name": "list_s3_buckets",
                    "description": (
                        "READ-ONLY. List S3 buckets in the AWS account."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },

            {
                "type": "function",
                "function": {
                    "name": "list_ec2_instances",
                    "description": (
                        "READ-ONLY. List EC2 instances in the AWS account."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },

            # ============================================================
            # TERRAFORM FILE
            # ============================================================

            {
                "type": "function",
                "function": {
                    "name": "write_terraform_file",
                    "description": (
                        "Create or overwrite a simple Terraform .tf file "
                        "inside the Terraform directory. For new resources "
                        "always prefer a new .tf file. Never overwrite "
                        "main.tf or backend.tf."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": (
                                    "Simple Terraform filename such as "
                                    "ec2.tf. Must end with .tf and must not "
                                    "contain directories or path traversal."
                                ),
                            },
                            "content": {
                                "type": "string",
                                "description": (
                                    "Complete Terraform configuration."
                                ),
                            },
                        },
                        "required": [
                            "filename",
                            "content",
                        ],
                    },
                },
            },

            # ============================================================
            # TERRAFORM COMMANDS
            # ============================================================

            {
                "type": "function",
                "function": {
                    "name": "terraform_fmt",
                    "description": (
                        "Run terraform fmt in the Terraform directory."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },

            {
                "type": "function",
                "function": {
                    "name": "terraform_init",
                    "description": (
                        "Run terraform init -reconfigure in the Terraform "
                        "directory."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },

            {
                "type": "function",
                "function": {
                    "name": "terraform_validate",
                    "description": (
                        "Run terraform validate in the Terraform directory."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },

            {
                "type": "function",
                "function": {
                    "name": "terraform_plan",
                    "description": (
                        "Run terraform plan -input=false. This only previews "
                        "changes and never applies infrastructure."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
        ]

    # ==================================================================
    # SAFETY FOR TERRAFORM FILENAMES
    # ==================================================================

    @staticmethod
    def _safe_filename(filename):

        if not filename:
            raise ValueError("filename is required")

        path = Path(filename)

        if path.name != filename:
            raise ValueError(
                "filename must be a simple filename without directories"
            )

        if path.suffix != ".tf":
            raise ValueError(
                "Only .tf Terraform files can be created"
            )

        protected_files = {
            "main.tf",
            "backend.tf",
        }

        if filename in protected_files:
            raise ValueError(
                f"Refusing to overwrite protected Terraform file: {filename}"
            )

        return filename

    # ==================================================================
    # TOOL EXECUTION
    # ==================================================================

    def execute_tool(self, tool_name, arguments):

        arguments = arguments or {}

        # --------------------------------------------------------------
        # AWS
        # --------------------------------------------------------------

        if tool_name == "get_aws_account":
            return get_aws_account()

        if tool_name == "list_s3_buckets":
            return list_s3_buckets()

        if tool_name == "list_ec2_instances":
            return list_ec2_instances()

        # --------------------------------------------------------------
        # TERRAFORM FILE
        # --------------------------------------------------------------

        if tool_name == "write_terraform_file":

            filename = self._safe_filename(
                arguments.get("filename")
            )

            content = arguments.get("content")

            if not content:
                raise ValueError(
                    "Terraform file content is required"
                )

            return write_terraform_file(
                filename,
                content,
            )

        # --------------------------------------------------------------
        # TERRAFORM COMMANDS
        # --------------------------------------------------------------

        if tool_name == "terraform_fmt":
            return terraform_fmt()

        if tool_name == "terraform_init":
            return terraform_init()

        if tool_name == "terraform_validate":
            return terraform_validate()

        if tool_name == "terraform_plan":
            return terraform_plan()

        raise ValueError(
            f"Unknown tool: {tool_name}"
        )

    # ==================================================================
    # TOOL ARGUMENT PARSER
    # ==================================================================

    @staticmethod
    def _parse_arguments(tool_call):

        function = tool_call.get(
            "function",
            {},
        )

        arguments = function.get(
            "arguments",
            {},
        )

        if isinstance(arguments, str):

            try:
                return json.loads(arguments)

            except json.JSONDecodeError:
                return {}

        return arguments or {}

    # ==================================================================
    # AGENT LOOP
    # ==================================================================

    def run(self, user_message):

        self.messages.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        max_rounds = 20

        for _ in range(max_rounds):

            response = ollama.chat(
                model=MODEL,
                messages=self.messages,
                tools=self.tools,
            )

            message = response["message"]

            tool_calls = message.get(
                "tool_calls"
            ) or []

            # ----------------------------------------------------------
            # FINAL RESPONSE
            # ----------------------------------------------------------

            if not tool_calls:

                answer = message.get(
                    "content",
                    "",
                ).strip()

                # If Qwen still tries to ask for confirmation after the
                # user explicitly authorized execution, send it back into
                # the tool loop.
                confirmation_phrases = (
                    "would you like me to",
                    "do you want me to",
                    "should i proceed",
                    "shall i proceed",
                    "would you like to proceed",
                    "do you want to proceed",
                )

                if any(
                    phrase in answer.lower()
                    for phrase in confirmation_phrases
                ):

                    self.messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Do not ask for confirmation. Continue the "
                                "original user request now. Execute the "
                                "available tools and report the actual "
                                "results."
                            ),
                        }
                    )

                    continue

                self.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                    }
                )

                return answer

            # ----------------------------------------------------------
            # TOOL CALLS
            # ----------------------------------------------------------

            self.messages.append(message)

            for tool_call in tool_calls:

                function = tool_call.get(
                    "function",
                    {},
                )

                tool_name = function.get(
                    "name"
                )

                arguments = self._parse_arguments(
                    tool_call
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
                        arguments,
                    )

                except Exception as exc:

                    result = {
                        "error": str(exc)
                    }

                print(
                    f"[Agent] Tool result: {result}"
                )

                self.messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(
                            result,
                            default=str,
                        ),
                    }
                )

        return (
            "The agent reached its maximum tool-execution rounds. "
            "No further action was taken."
        )


# ======================================================================
# MAIN
# ======================================================================

def main():

    agent = DevOpsAgent()

    print(
        "AI DevOps Agent started."
    )

    print(
        f"Model: {MODEL}"
    )

    print(
        f"Terraform directory: {TERRAFORM_DIR}"
    )

    print(
        "Type 'exit' or 'quit' to stop.\n"
    )

    while True:

        try:

            user_message = input(
                "You: "
            ).strip()

        except (
            EOFError,
            KeyboardInterrupt,
        ):

            print(
                "\nExiting."
            )

            break

        if not user_message:
            continue

        if user_message.lower() in {
            "exit",
            "quit",
        }:

            print(
                "Exiting."
            )

            break

        try:

            answer = agent.run(
                user_message
            )

            print(
                f"\nAgent: {answer}\n"
            )

        except Exception as exc:

            print(
                f"\nAgent error: {exc}\n"
            )


if __name__ == "__main__":
    main()
