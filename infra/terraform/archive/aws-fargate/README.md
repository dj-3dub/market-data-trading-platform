# Archived Fargate scaffold — do not deploy

This early learning scaffold is retained for project history. It uses dummy
provider credentials, lacks Kafka and the strategy engine, references Compose
hostnames without ECS discovery, and permits a port the applications do not use.
It is excluded from the active Make and CI Terraform checks.

Use [aws-managed](../../envs/aws-managed/README.md) for the current AWS design.
That environment still requires account-level deployment and recovery validation.
