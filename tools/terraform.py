import subprocess
from pathlib import Path


TERRAFORM_DIR = Path("terraform")


def run_command(command):

    result = subprocess.run(
        command,
        cwd=TERRAFORM_DIR,
        capture_output=True,
        text=True
    )

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr
    }


def terraform_fmt():

    return run_command(
        ["terraform", "fmt"]
    )


def terraform_init():

    return run_command(
        ["terraform", "init"]
    )


def terraform_validate():

    return run_command(
        ["terraform", "validate"]
    )


def terraform_plan():

    return run_command(
        ["terraform", "plan"]
    )


def write_terraform_file(filename, content):

    file_path = TERRAFORM_DIR / filename

    file_path.write_text(content)

    return {
        "status": "success",
        "file": str(file_path)
    }
