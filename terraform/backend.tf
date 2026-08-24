terraform {
  backend "s3" {
    bucket       = "ai-devops-agent-terraform-state-444083008248"
    key          = "terraform.tfstate"
    region       = "ap-south-1"
    use_lockfile = true
  }
}
