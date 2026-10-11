# Managed AWS reliability environment

This environment defines three-AZ **provisioned MSK**, private ECS Fargate
services, Cloud Map discovery, a public HTTPS ALB, AMP remote-write collection,
SLO/component rules and Managed Grafana. It is separate from the older
[archived Fargate scaffold](../../archive/aws-fargate/README.md). Terraform validation is not proof of a successful AWS
deployment; account-level deployment and baseline measurement are still needed.

## Inputs and bootstrap

Provide an existing VPC, three private subnets in distinct AZs with NAT or all
required endpoints, public ALB subnets, a regional ACM certificate, a DNS name,
and IAM Identity Center user IDs. Enable IAM Identity Center before creating
Managed Grafana. Use a dedicated test account/environment for experiments.

Create an encrypted/versioned S3 state bucket and a DynamoDB lock table with a
string partition key `LockID`. Initialize with:

```sh
terraform init -backend-config=bucket=YOUR_STATE_BUCKET \
  -backend-config=key=trading-reliability/terraform.tfstate \
  -backend-config=region=us-east-1 \
  -backend-config=dynamodb_table=YOUR_LOCK_TABLE -backend-config=encrypt=true
```

Supply values matching `variables.tf` in a local ignored `*.auto.tfvars.json`.
Images must have SHA256 digests. For first-time ECR bootstrap, provide syntactically
valid placeholder digest URIs and apply only `-target=aws_ecr_repository.services`.
Then publish images and replace placeholders before a full plan/apply. The full
deployment must never use placeholder images.

The GitHub `aws-test` environment needs:

| Variable | Value |
|---|---|
| `AWS_REGION` | Deployment region |
| `AWS_PROJECT_NAME` | Same value as Terraform `name` |
| `AWS_DEPLOY_ROLE_ARN` | Existing GitHub OIDC deployment role |
| `TF_STATE_BUCKET`, `TF_STATE_LOCK_TABLE` | Backend resources |
| `AWS_TERRAFORM_INPUTS_JSON` | JSON object with all Terraform inputs except images |
| `API_HOSTNAME` | Same DNS name as Terraform `api_hostname` |

Configure the AWS GitHub OIDC provider and role trust for the exact repository
and subject `repo:OWNER/REPO:environment:aws-test`, audience `sts.amazonaws.com`.
Its permission policy must allow managing this environment's ECS, MSK, ELB,
Cloud Map, IAM roles/pass-role, ECR, logs, AMP, Grafana and backend resources.
Bootstrap this account-specific deployment identity separately from the stack
it manages. The workflow uses temporary credentials, runs contract tests, builds
and pushes once per commit, resolves immutable digests, plans/applies and probes
the public strategy route. It does not run automatically on PRs.

Point `api_hostname` at output `alb_dns_name`. Until DNS resolves and the
certificate matches, the external-path probe correctly reports failures.

## Operational choices

- MSK uses TLS on 9094 with network-restricted unauthenticated clients. Access is
  limited to the ECS security group; Kafka IAM/SASL authorization is not enabled.
- One partition and one active strategy are assumed. Priority 2 introduces local
  SQLite state for producer and strategy in Compose. These Fargate definitions
  do not yet mount durable application state: do not claim task-replacement
  durability or deploy the Priority 2 images here until AWS persistence is designed.
  Strategy/producer/collector replacements stop the old task first. Expect
  deployment gaps; measure them against the provisional objectives.
- API has two replicas and rolling deployment with ECS rollback on failed rollout.
  ALB checks liveness so dependency outages do not remove all targets at once.
- Collector DNS discovery enumerates task IPs; samples go to AMP using the task
  role and SigV4. Its temporary local WAL can lose unshipped samples on task loss;
  coverage alerts are essential. The probe independently traverses public ingress.
- AMP owns rule evaluation. Managed Grafana administrators must add the AMP
  datasource (SigV4, this region) and import the repository's dashboard JSON.
  Set that datasource as default for the Reliability dashboard.
- No Kafka exporter is deployed here yet; the Kafka backlog component rule has
  no AWS input until one is added. CloudWatch/MSK monitoring and source freshness
  provide initial broker diagnosis.
- The frontend remains available in Compose; AWS currently exposes the API and
  managed dashboards. The optional privileged eBPF agent requires EC2/native Linux.

MSK brokers, NAT gateways, ALB, Fargate, AMP ingestion and Grafana users incur
ongoing charges. Size and cost-review the plan for the selected region before
applying. This configuration has no account-specific cost ceiling.

## Acceptance

After deployment: verify fresh increasing timestamps, all four application/probe
scrape jobs in AMP, SLO recording series, sample coverage, Grafana queries and
task rollout events. Collect at least a representative baseline before treating
500 ms as a release constraint. Exercise task restart and broker/network faults
in this environment before claiming AWS recovery guarantees. Restore a previous
image digest map and apply to roll back an application release.

An executable AWS task replacement experiment is provided:

```sh
python3 scripts/aws-restart-experiment.py --cluster trading-reliability \
  --service strategy-engine --url https://YOUR_API_HOSTNAME
```

Run from the repository root with AWS CLI credentials for the test account.
It requires a healthy baseline, stops one task (ECS replaces it automatically),
and requires a replacement task plus three advancing fresh responses. Evidence
is written to `artifacts/`. Supported services are market-data, strategy-engine
and api-gateway. No desired-count changes are made. Broker FIS and latency proxy
experiments remain follow-up AWS validation work.
