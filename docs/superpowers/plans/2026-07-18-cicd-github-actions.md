# CI/CD GitHub Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build 8 Docker images trên GitHub Actions, push lên ECR theo tag git SHA, và deploy tự động lên VM qua kênh S3 + SSM khi merge vào `main`.

**Architecture:** Artifact (image) đi qua ECR, config đi qua S3 — hai kênh tách biệt. PR chỉ build để xác minh, không chạm AWS. Chỉ `main` có quyền push ECR và deploy, siết bằng OIDC trust policy. VM không build gì nữa, chỉ `pull`.

**Tech Stack:** GitHub Actions, AWS ECR, AWS SSM (`AWS-RunShellScript`), S3, Terraform (AWS provider `~> 5.0`, TF `>= 1.5`), Docker Compose v2, Ruff, `docker/build-push-action` với cache `type=gha`.

**Spec:** `docs/superpowers/specs/2026-07-18-cicd-github-actions-design.md`

## Global Constraints

- `project` = `shbexpert`, `region` = `ap-southeast-1` (mặc định trong `infra/variables.tf`)
- Repo slug: `TruongSon421/dashmint_ai`
- 8 service ứng dụng: `api`, `worker`, `web`, `tools-mock`, `mcp-deterministic`, `mcp-rag`, `mcp-external`, `mcp-state`
- Tag image = git SHA đầy đủ (`github.sha`). **Không** dùng `latest` cho production
- Mọi lệnh compose trên VM phải giữ `-f docker-compose.yml -f docker-compose.prod.yml`
- `.env` production nằm ở `/opt/shbexpert/.env`, không có trong git/tarball. **Không bao giờ** xoá thư mục hay dùng `rsync --delete` khi triển khai
- Chỉ 2 GitHub repo **variables** (không phải secrets): `AWS_ROLE_ARN`, `AWS_REGION`
- `scripts/` chỉ có trong image `api` và `mcp-rag` — mọi bước seed/migrate phải chạy qua hai service này
- Làm việc trên nhánh `devops/cloud-deploy`

---

### Task 1: Làm thông kênh S3 + SSM bằng tay

Kênh này **chưa từng chạy** (spec §1) — VM không có AWS CLI và không có script nào gọi `aws s3`. Task này chứng minh kênh hoạt động trước khi bất kỳ workflow nào phụ thuộc vào nó. Nếu bước này gãy, mọi task sau đều vô nghĩa.

**Files:**
- Modify: `infra/user_data.sh` (thêm awscli, sửa comment dòng 3)
- Create: `docs/runbooks/s3-ssm-channel.md`

**Interfaces:**
- Consumes: hạ tầng có sẵn từ commit `56e67f0` — bucket `shbexpert-deploy-<account_id>`, IAM role `shbexpert-ssm-role`, instance profile đã gắn
- Produces: xác nhận VM có `aws` CLI và đọc được bucket deploy; runbook cho các task sau tái sử dụng

- [ ] **Step 1: Lấy các định danh hạ tầng**

```bash
cd infra
terraform output -raw deploy_bucket   # vd: shbexpert-deploy-123456789012
terraform output -raw instance_id     # vd: i-0abc123def456
terraform output -raw app_domain      # vd: app.13-215-1-2.sslip.io
```

Ghi lại 3 giá trị này — dùng suốt task.

- [ ] **Step 2: Xác nhận VM chưa có AWS CLI (baseline)**

```bash
aws ssm send-command \
  --document-name AWS-RunShellScript \
  --instance-ids <INSTANCE_ID> \
  --parameters 'commands=["which aws || echo NO_AWS_CLI"]' \
  --query 'Command.CommandId' --output text
```

Lấy `CommandId` rồi đọc kết quả:

```bash
aws ssm get-command-invocation \
  --command-id <COMMAND_ID> --instance-id <INSTANCE_ID> \
  --query '{Status:Status,Out:StandardOutputContent,Err:StandardErrorContent}'
```

Expected: `Status: Success`, `Out: NO_AWS_CLI`.

Nếu `send-command` báo `InvalidInstanceId`, SSM agent chưa đăng ký — kiểm tra `aws ssm describe-instance-information` trước khi đi tiếp.

- [ ] **Step 3: Cài AWS CLI lên VM đang chạy**

`user_data.sh` chỉ chạy lúc tạo instance, nên VM hiện tại phải cài tay:

```bash
aws ssm send-command \
  --document-name AWS-RunShellScript \
  --instance-ids <INSTANCE_ID> \
  --parameters 'commands=["apt-get update -qq && apt-get install -y -qq unzip curl","curl -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o /tmp/awscliv2.zip","unzip -q -o /tmp/awscliv2.zip -d /tmp && /tmp/aws/install --update","rm -rf /tmp/awscliv2.zip /tmp/aws","/usr/local/bin/aws --version"]' \
  --query 'Command.CommandId' --output text
```

Đọc kết quả bằng lệnh `get-command-invocation` ở Step 2.
Expected: `Status: Success`, output chứa `aws-cli/2.`

- [ ] **Step 4: Đẩy một tarball thử lên S3 từ máy local**

```bash
cd /home/son/AIC/dashmint_ai
tar -czf /tmp/probe.tar.gz docker-compose.yml docker-compose.prod.yml deploy/ postgres/
aws s3 cp /tmp/probe.tar.gz s3://<DEPLOY_BUCKET>/deploys/probe.tar.gz
aws s3 ls s3://<DEPLOY_BUCKET>/deploys/
```

Expected: dòng liệt kê `probe.tar.gz` với kích thước > 0.

- [ ] **Step 5: Kéo tarball về VM và giải nén — phép thử quyết định**

Đây là bước chứng minh instance role đọc được bucket:

```bash
aws ssm send-command \
  --document-name AWS-RunShellScript \
  --instance-ids <INSTANCE_ID> \
  --parameters 'commands=["set -euo pipefail","cd /opt/shbexpert","ls -la .env","aws s3 cp s3://<DEPLOY_BUCKET>/deploys/probe.tar.gz /tmp/probe.tar.gz","tar -xf /tmp/probe.tar.gz -C /opt/shbexpert","rm /tmp/probe.tar.gz","ls -la .env docker-compose.yml"]' \
  --query 'Command.CommandId' --output text
```

Expected: `Status: Success`, và **`.env` vẫn còn** ở cả hai lần `ls`.

`ls -la .env` xuất hiện hai lần là có chủ đích — chứng minh giải nén bằng `tar -xf` không xoá secret production.

Nếu bước `aws s3 cp` fail với `AccessDenied`: kiểm tra `aws_iam_role_policy.ssm_s3_read` trong `infra/s3.tf` có đúng bucket ARN không.

- [ ] **Step 6: Sửa `infra/user_data.sh` để instance mới có sẵn AWS CLI**

Sửa comment dòng 2-3, vì "we deploy manually without CI/CD" sắp không còn đúng:

```bash
#!/bin/bash
# Bootstrap Docker Engine + Compose + AWS CLI on Ubuntu 24.04. Code is
# shipped by the deploy workflow (tarball via S3, extracted over SSM);
# container images come from ECR. See docs/superpowers/specs/
# 2026-07-18-cicd-github-actions-design.md
```

Thêm bước cài AWS CLI ngay sau dòng `apt-get install -y ca-certificates curl rsync git` (dòng 8):

```bash
# AWS CLI v2 — needed to pull the deploy tarball from S3 and to
# authenticate against ECR. Not in Ubuntu's apt repos, hence the zip.
curl -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o /tmp/awscliv2.zip
apt-get install -y unzip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install
rm -rf /tmp/awscliv2.zip /tmp/aws
```

- [ ] **Step 7: Ghi runbook**

Tạo `docs/runbooks/s3-ssm-channel.md` với nội dung: mục đích kênh, 3 lệnh lấy định danh (Step 1), mẫu `send-command` + `get-command-invocation` (Step 2), và cách chẩn đoán hai lỗi đã gặp (`InvalidInstanceId`, `AccessDenied`). Các task sau tham chiếu file này thay vì lặp lại lệnh.

- [ ] **Step 8: Dọn tarball thử và commit**

```bash
aws s3 rm s3://<DEPLOY_BUCKET>/deploys/probe.tar.gz
git add infra/user_data.sh docs/runbooks/s3-ssm-channel.md
git commit -m "feat(infra): cài AWS CLI trên VM, xác minh kênh deploy S3+SSM

Kênh S3+SSM từ 56e67f0 mới có hạ tầng, chưa từng chạy vì VM thiếu
AWS CLI. Xác minh end-to-end bằng tay: đẩy tarball lên S3, kéo về qua
SSM, giải nén — .env production còn nguyên."
```

---

### Task 2: Ruff config + workflow CI

Task này độc lập với đường deploy và cho giá trị ngay. Quan trọng hơn: job `build` chứng minh cả 8 Dockerfile build được trên GitHub Actions — điều mà Task 7 phụ thuộc hoàn toàn.

**Files:**
- Modify: `pyproject.toml`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: không có (độc lập)
- Produces: ma trận 8 service dùng lại ở Task 7; xác nhận build context `.` + `<svc>/Dockerfile` hoạt động trên runner

- [ ] **Step 1: Thêm config Ruff vào `pyproject.toml`**

Thêm vào cuối file (sau block `[tool.pytest.ini_options]`):

```toml
[tool.ruff]
target-version = "py311"
line-length = 100
exclude = ["web", ".venv", "artifacts"]

[tool.ruff.lint]
# Khởi đầu bảo thủ: pycodestyle, pyflakes, isort, pyupgrade.
# Repo chưa từng chạy linter nên siết mạnh sẽ ra hàng trăm lỗi.
select = ["E", "F", "I", "UP"]
ignore = ["E501"]  # line-length do formatter lo
```

- [ ] **Step 2: Chạy Ruff local để biết mức độ nợ hiện có**

```bash
pipx run ruff check . 2>&1 | tail -5
```

Expected: một con số lỗi cụ thể. **Không sửa code ứng dụng trong task này.**

Nếu > 50 lỗi: thêm `"--exit-zero"` vào bước CI ở Step 3 và ghi TODO vào commit message, để CI không đỏ ngay từ ngày đầu vì nợ có sẵn. Nếu ≤ 50: sửa luôn bằng `ruff check --fix .` và commit riêng.

- [ ] **Step 3: Tạo `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [develop]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint-python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/ruff-action@v3
        with:
          args: check --output-format=github

  lint-web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: web/package.json
      - run: npm install
      - run: npx tsc --noEmit
      - run: npm run lint

  build:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        service:
          - api
          - worker
          - web
          - tools-mock
          - mcp-deterministic
          - mcp-rag
          - mcp-external
          - mcp-state
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v6
        with:
          context: .
          file: ${{ matrix.service }}/Dockerfile
          push: false
          cache-from: type=gha,scope=${{ matrix.service }}
          cache-to: type=gha,mode=max,scope=${{ matrix.service }}

  test:
    runs-on: ubuntu-latest
    env:
      LLM_MOCK: "true"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install pytest
      # Repo chưa có test nào — dự án B sẽ thêm vào tests/.
      # --co xác nhận pytest chạy được; exit code 5 = "no tests collected",
      # là trạng thái hợp lệ hiện tại, không phải lỗi.
      - run: pytest --co -q || [ $? -eq 5 ]
```

`scope=${{ matrix.service }}` là bắt buộc — không có nó, 8 service dùng chung một cache và ghi đè lẫn nhau.

- [ ] **Step 4: Commit và mở PR thử**

```bash
git add pyproject.toml .github/workflows/ci.yml
git commit -m "ci: thêm workflow CI (ruff, tsc, build 8 image, pytest scaffold)"
git push -u origin devops/cloud-deploy
gh pr create --base develop --title "ci: thêm quality gate" \
  --body "Thêm ci.yml: ruff, next lint + tsc, build 8 image, pytest scaffold cho dự án B."
```

- [ ] **Step 5: Xác minh CI xanh**

```bash
gh pr checks --watch
```

Expected: cả 4 job pass. Job `build` chạy 8 lần song song.

Nếu một service fail: đọc log, sửa Dockerfile hoặc `.dockerignore`. **Không** merge khi build đỏ — Task 7 dựa hoàn toàn vào việc 8 build này chạy được.

---

### Task 3: Terraform — ECR repositories + quyền pull cho VM

**Files:**
- Create: `infra/ecr.tf`

**Interfaces:**
- Consumes: `aws_iam_role.ssm` từ `infra/iam.tf`, `var.project`
- Produces: `aws_ecr_repository.app` (map key = tên service) — Task 4 tham chiếu ARN của nó

- [ ] **Step 1: Tạo `infra/ecr.tf`**

```hcl
# Một repository cho mỗi service ứng dụng. Ảnh được build trên GitHub
# Actions và tag theo git SHA — VM chỉ pull, không build.
locals {
  services = toset([
    "api", "worker", "web", "tools-mock",
    "mcp-deterministic", "mcp-rag", "mcp-external", "mcp-state",
  ])
}

resource "aws_ecr_repository" "app" {
  for_each = local.services

  name                 = "${var.project}/${each.key}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Không có policy này thì ECR phình vô hạn. 10 ảnh ≈ 10 lần deploy gần
# nhất — cũng chính là giới hạn rollback (spec §8).
resource "aws_ecr_lifecycle_policy" "app" {
  for_each   = aws_ecr_repository.app
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

# VM role hiện chỉ có SSM core + s3 read. Không có policy này thì
# `docker compose pull` trên VM trả 401 và cả thiết kế không chạy được.
resource "aws_iam_role_policy" "ssm_ecr_pull" {
  name = "${var.project}-ecr-pull"
  role = aws_iam_role.ssm.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # GetAuthorizationToken không hỗ trợ resource-level permission.
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability",
        ]
        Resource = [for r in aws_ecr_repository.app : r.arn]
      },
    ]
  })
}

output "ecr_registry" {
  description = "Registry host — <account>.dkr.ecr.<region>.amazonaws.com"
  value       = split("/", values(aws_ecr_repository.app)[0].repository_url)[0]
}
```

`image_tag_mutability = "IMMUTABLE"` là chốt kỹ thuật cho lời hứa ở spec §8: ECR sẽ **từ chối** mọi lần push đè lên tag đã tồn tại.

**Đánh đổi cần biết trước.** Nếu `build-push` fail giữa chừng (vd service thứ 6 hỏng khi 5 service đầu đã push xong), chạy lại workflow ở **cùng SHA** có thể bị ECR từ chối vì tag đã tồn tại. Hành vi của ECR khi push lại đúng digest cũ lên tag IMMUTABLE là chỗ tôi **không chắc** — cần quan sát lần đầu gặp.

Đường lui luôn dùng được: đẩy một commit rỗng để có SHA mới.

```bash
git commit --allow-empty -m "chore: trigger rebuild"
git push
```

- [ ] **Step 2: Plan và apply**

```bash
cd infra
terraform fmt
terraform validate
terraform plan
```

Expected: `17 to add, 0 to change, 0 to destroy` — 8 repository + 8 lifecycle policy + 1 role policy. Output mới (`ecr_registry`) hiện ở mục "Changes to Outputs" riêng, **không** tính vào số resource.

```bash
terraform apply
```

- [ ] **Step 3: Xác minh VM đăng nhập và pull được từ ECR**

Đây là bước kiểm chứng quan trọng nhất của task. Đẩy một ảnh nhỏ lên rồi bắt VM kéo về:

```bash
REGISTRY=$(terraform output -raw ecr_registry)
aws ecr get-login-password --region ap-southeast-1 \
  | docker login --username AWS --password-stdin "$REGISTRY"
docker pull alpine:3.20
docker tag alpine:3.20 "$REGISTRY/shbexpert/api:probe"
docker push "$REGISTRY/shbexpert/api:probe"
```

Rồi từ VM:

```bash
aws ssm send-command \
  --document-name AWS-RunShellScript \
  --instance-ids <INSTANCE_ID> \
  --parameters 'commands=["set -euo pipefail","aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin <REGISTRY>","docker pull <REGISTRY>/shbexpert/api:probe","docker rmi <REGISTRY>/shbexpert/api:probe"]' \
  --query 'Command.CommandId' --output text
```

Expected: `Status: Success`. Nếu `401 Unauthorized` → policy `ssm_ecr_pull` chưa hiệu lực; nếu `aws: command not found` → Task 1 chưa xong.

- [ ] **Step 4: Dọn ảnh thử và commit**

```bash
aws ecr batch-delete-image \
  --repository-name shbexpert/api \
  --image-ids imageTag=probe
git add infra/ecr.tf
git commit -m "feat(infra): ECR repositories + quyền pull cho VM

8 repository tag IMMUTABLE, lifecycle giữ 10 ảnh. Role SSM của VM
trước đây không có quyền ECR nào — thiếu nó thì docker compose pull
trả 401."
```

---

### Task 4: Terraform — tag instance + GitHub OIDC role

**Files:**
- Modify: `infra/compute.tf:20`
- Create: `infra/github_oidc.tf`

**Interfaces:**
- Consumes: `aws_ecr_repository.app` (Task 3), `aws_s3_bucket.deploy` (`infra/s3.tf`)
- Produces: output `github_actions_role_arn` — giá trị điền vào GitHub variable `AWS_ROLE_ARN` ở Task 7

- [ ] **Step 1: Merge tag `Project` vào instance**

Sửa `infra/compute.tf` dòng 20. Terraform thay **nguyên khối** map tags, nên phải giữ `Name` — mất nó thì instance mất tên trong console và gãy mọi công cụ tham chiếu theo tên:

```hcl
  tags = {
    Name    = "${var.project}-vm"
    Project = var.project
    Role    = "app"
  }
```

- [ ] **Step 2: Tạo `infra/github_oidc.tf`**

```hcl
# Cho phép GitHub Actions lấy credential tạm qua OIDC — không có access
# key tĩnh nào tồn tại trong hệ thống.
data "aws_caller_identity" "gh" {}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Chỉ nhánh main. PR (kể cả từ fork) không lấy được credential.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:TruongSon421/dashmint_ai:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

resource "aws_iam_role_policy" "github_actions" {
  name = "${var.project}-github-actions"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        # Thiếu một action ở đây sẽ fail SAU khi đã upload xong layer —
        # tốn băng thông và báo lỗi rất khó hiểu.
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
        ]
        Resource = [for r in aws_ecr_repository.app : r.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.deploy.arn}/deploys/*"
      },
      {
        # SendCommand phải authorize CẢ document lẫn instance. Hai
        # statement tách rời, KHÔNG gộp làm một: IAM áp Condition cho
        # mọi Resource trong cùng statement, mà document managed của AWS
        # không có tag nào — aws:ResourceTag/Project sẽ vắng mặt,
        # StringEquals trả false, statement không áp dụng cho document,
        # và cả lệnh bị implicit deny dù instance đúng tag.
        Effect   = "Allow"
        Action   = ["ssm:SendCommand"]
        Resource = ["arn:aws:ssm:${var.region}::document/AWS-RunShellScript"]
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:SendCommand"]
        Resource = ["arn:aws:ec2:${var.region}:${data.aws_caller_identity.gh.account_id}:instance/*"]
        Condition = {
          StringEquals = { "aws:ResourceTag/Project" = var.project }
        }
      },
      {
        # SendCommand chỉ trả CommandId. Không có quyền này thì workflow
        # không đọc được exit code và sẽ báo thành công kể cả khi
        # deploy.sh chết.
        Effect   = "Allow"
        Action   = ["ssm:GetCommandInvocation"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:DescribeInstances", "ec2:DescribeAddresses"]
        Resource = "*"
      },
    ]
  })
}

output "github_actions_role_arn" {
  description = "Điền vào GitHub repo variable AWS_ROLE_ARN."
  value       = aws_iam_role.github_actions.arn
}
```

`ec2:DescribeInstances` và `ec2:DescribeAddresses` không hỗ trợ resource-level permission, nên bắt buộc `Resource = "*"`.

- [ ] **Step 3: Plan, kiểm tra instance không bị recreate, rồi apply**

```bash
cd infra
terraform fmt && terraform validate
terraform plan
```

Expected: `aws_instance.app` phải hiện `~ update in-place`, **không phải** `-/+ destroy and then create`. Tag là thuộc tính update in-place; nếu thấy `destroy` thì có gì đó khác đã đổi — dừng lại và điều tra, đừng apply.

```bash
terraform apply
terraform output -raw github_actions_role_arn
```

- [ ] **Step 4: Xác minh discovery hoạt động**

Chạy đúng các lệnh mà workflow sẽ chạy ở Task 7:

```bash
aws ec2 describe-instances \
  --filters "Name=tag:Project,Values=shbexpert" \
            "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text

aws ec2 describe-addresses \
  --filters "Name=tag:Name,Values=shbexpert-eip" \
  --query 'Addresses[0].PublicIp' --output text
```

Expected: instance ID khớp `terraform output -raw instance_id`, và IP khớp `terraform output -raw public_ip`. Nếu trả `None` → tag chưa được apply.

- [ ] **Step 5: Commit**

```bash
git add infra/compute.tf infra/github_oidc.tf
git commit -m "feat(infra): OIDC role cho GitHub Actions + tag Project cho VM

Trust policy khoá theo ref:refs/heads/main — PR từ fork không lấy được
credential. Tag Project để workflow discover instance lúc chạy thay vì
hardcode ID (ID đổi mỗi lần Terraform replace instance)."
```

---

### Task 5: `docker-compose.yml` — thêm `image:`

**Files:**
- Modify: `docker-compose.yml` (8 service ứng dụng)

**Interfaces:**
- Consumes: naming convention `${var.project}/<service>` từ Task 3
- Produces: biến `REGISTRY` và `IMAGE_TAG` mà Task 6 và Task 7 truyền vào

- [ ] **Step 1: Thêm `image:` cho cả 8 service**

Với mỗi service có `build:`, thêm dòng `image:` ngay phía trên. Ví dụ cho `api`:

```yaml
  api:
    image: ${REGISTRY:-shbexpert}/shbexpert/api:${IMAGE_TAG:-dev}
    build:
      context: .
      dockerfile: api/Dockerfile
```

Áp dụng cùng mẫu cho `tools-mock`, `mcp-deterministic`, `mcp-rag`, `mcp-external`, `mcp-state`, `worker`, `web` — đổi phần cuối đường dẫn theo tên service.

Giữ cả hai key là có chủ đích: dev local `docker compose up` vẫn build (compose chỉ build khi image chưa có local, không tự pull với service có `build:`); prod `pull` + `up --no-build`.

Default `shbexpert/shbexpert/api:dev` là namespace không tồn tại trên Docker Hub — cố ý, để `docker compose pull` ngoài prod fail ngay thay vì kéo nhầm.

- [ ] **Step 2: Xác minh interpolation đúng ở cả hai chế độ**

```bash
docker compose config | grep "image:"
```

Expected: 8 dòng dạng `image: shbexpert/shbexpert/<svc>:dev`, cộng các image public (`postgres:16`, `redis:7`, ...).

```bash
REGISTRY=123456789012.dkr.ecr.ap-southeast-1.amazonaws.com IMAGE_TAG=abc123 \
  docker compose config | grep "image:"
```

Expected: 8 dòng dạng `image: 123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/shbexpert/<svc>:abc123`.

- [ ] **Step 3: Xác minh dev flow không gãy**

```bash
docker compose build api
docker compose config --services | wc -l
```

Expected: build thành công; 12 service.

Ảnh local giờ được tag `shbexpert/shbexpert/api:dev` thay vì `shbexpert-flow-api` như trước — ảnh cũ thành mồ côi, dev sẽ build lại một lần. Đây là thay đổi mong đợi, không phải lỗi.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: thêm image: vào 8 service để pull từ ECR

Giữ cả image: lẫn build: — một file compose phục vụ cả dev (build tại
chỗ) lẫn prod (pull theo SHA), không phải duy trì hai bản lệch nhau."
```

---

### Task 6: `deploy.sh` — pull thay vì build

**Files:**
- Modify: `deploy/deploy.sh`

**Interfaces:**
- Consumes: `AWS_REGION`, `ECR_REGISTRY`, `IMAGE_TAG` từ process env (Task 7 inline vào lệnh SSM); `image:` từ Task 5
- Produces: script mà lệnh SSM ở Task 7 gọi

- [ ] **Step 1: Viết lại `deploy/deploy.sh`**

```bash
#!/usr/bin/env bash
# Runs ON the VM, in /opt/shbexpert. Pulls pre-built images from ECR,
# brings the stack up, then applies DB migrations and seeds demo data.
# Safe to re-run (compose is idempotent; migrations are versioned).
#
# Images are built by GitHub Actions, not here — this script never
# builds. It also never touches S3: the deploy workflow's SSM command
# fetches and extracts the config tarball before calling this. Keeping
# that split means a manual re-run over an SSM session is just
# `bash deploy/deploy.sh`, no tarball rebuild needed.
#
# Required in the environment:
#   AWS_REGION    e.g. ap-southeast-1
#   ECR_REGISTRY  <account>.dkr.ecr.<region>.amazonaws.com
#   IMAGE_TAG     git SHA — cannot be derived on the VM, must be passed
set -euo pipefail
cd "$(dirname "$0")/.."

: "${AWS_REGION:?AWS_REGION is required}"
: "${ECR_REGISTRY:?ECR_REGISTRY is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

export REGISTRY="$ECR_REGISTRY"

# The prod overlay adds Caddy — the only internet-facing service. Drop
# the -f and there is no TLS and nothing reachable from outside.
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

echo ">> Logging in to ECR ($ECR_REGISTRY)..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo ">> Pulling images at tag $IMAGE_TAG..."
$COMPOSE pull

echo ">> Starting stack..."
$COMPOSE up -d --no-build

echo ">> Waiting for api to become healthy..."
for _ in $(seq 1 60); do
  if $COMPOSE ps api | grep -q "healthy"; then echo "api healthy"; break; fi
  sleep 5
done

echo ">> DB migrations (alembic)..."
$COMPOSE run --rm api alembic upgrade head

# seed_policies must run in mcp-rag (it has fastembed + the pre-warmed
# embedding model cache); the golden cases run in api. Only these two
# images carry scripts/ — see api/Dockerfile and mcp-rag/Dockerfile.
echo ">> Seeding policy pack into qdrant (mcp-rag)..."
$COMPOSE run --rm mcp-rag python -m scripts.seed_policies

echo ">> Seeding golden cases (api)..."
for c in c06 c07 c08; do
  $COMPOSE run --rm api python -m scripts.seed_case_"$c"
done

echo ">> Done. Current state:"
$COMPOSE ps
```

Ba dòng `: "${VAR:?...}"` là bảo hiểm cho lỗi nguy hiểm nhất: nếu `IMAGE_TAG` không tới nơi, script dừng ngay với thông báo rõ ràng thay vì âm thầm deploy tag `dev`.

- [ ] **Step 2: Kiểm tra cú pháp**

```bash
bash -n deploy/deploy.sh
shellcheck deploy/deploy.sh || true
```

Expected: `bash -n` không in gì.

- [ ] **Step 3: Xác minh script từ chối chạy khi thiếu biến**

```bash
bash deploy/deploy.sh 2>&1 | head -2
```

Expected: `AWS_REGION is required`, exit code khác 0.

- [ ] **Step 4: Commit**

```bash
git add deploy/deploy.sh
git commit -m "feat(deploy): pull ảnh từ ECR thay vì build trên VM

VM không còn build 8 image mỗi lần deploy. Script yêu cầu tường minh
AWS_REGION/ECR_REGISTRY/IMAGE_TAG — IMAGE_TAG không thể suy ra trên VM,
thiếu nó phải dừng chứ không được rơi về tag dev."
```

---

### Task 7: Workflow deploy

Task cuối, phụ thuộc tất cả các task trước.

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: ECR repos (Task 3), OIDC role (Task 4), `image:` (Task 5), `deploy.sh` (Task 6), ma trận 8 service (Task 2)
- Produces: deploy tự động khi push `main`; rollback qua `workflow_dispatch`

- [ ] **Step 1: Tạo 2 GitHub repo variables**

```bash
gh variable set AWS_REGION --body "ap-southeast-1"
gh variable set AWS_ROLE_ARN --body "$(cd infra && terraform output -raw github_actions_role_arn)"
gh variable list
```

Dùng `variable` chứ không phải `secret`: đây là định danh công khai, và secret bị mask trong log khiến deploy lỗi rất khó chẩn đoán.

- [ ] **Step 2: Tạo `.github/workflows/deploy.yml`**

```yaml
name: Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      image_tag:
        description: "Git SHA để rollback về (bỏ trống = deploy HEAD hiện tại)"
        required: true

# Hai lần merge sát nhau sẽ giẫm chân nhau trên cùng một VM. Không huỷ
# lần đang chạy — dừng giữa chừng nguy hiểm hơn là xếp hàng.
concurrency:
  group: deploy-production
  cancel-in-progress: false

permissions:
  id-token: write
  contents: read

jobs:
  build-push:
    # Rollback không build lại: ảnh đã nằm sẵn trên ECR.
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    strategy:
      fail-fast: true
      matrix:
        service:
          - api
          - worker
          - web
          - tools-mock
          - mcp-deterministic
          - mcp-rag
          - mcp-external
          - mcp-state
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}

      - uses: aws-actions/amazon-ecr-login@v2
        id: ecr

      - uses: docker/setup-buildx-action@v3

      - uses: docker/build-push-action@v6
        with:
          context: .
          file: ${{ matrix.service }}/Dockerfile
          push: true
          tags: ${{ steps.ecr.outputs.registry }}/shbexpert/${{ matrix.service }}:${{ github.sha }}
          cache-from: type=gha,scope=${{ matrix.service }}
          cache-to: type=gha,mode=max,scope=${{ matrix.service }}

  deploy:
    needs: build-push
    # build-push bị skip khi rollback. Không có always() thì deploy skip
    # theo và rollback sẽ báo xanh mà không làm gì cả.
    if: always() && needs.build-push.result != 'failure' && needs.build-push.result != 'cancelled'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}

      - name: Resolve image tag
        run: |
          TAG="${{ github.event.inputs.image_tag || github.sha }}"
          echo "IMAGE_TAG=$TAG" >> "$GITHUB_ENV"
          echo "Deploying tag: $TAG"

      - name: Discover infra
        run: |
          set -euo pipefail
          ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
          echo "ECR_REGISTRY=$ACCOUNT.dkr.ecr.${{ vars.AWS_REGION }}.amazonaws.com" >> "$GITHUB_ENV"
          echo "DEPLOY_BUCKET=shbexpert-deploy-$ACCOUNT" >> "$GITHUB_ENV"

          INSTANCE_ID=$(aws ec2 describe-instances \
            --filters "Name=tag:Project,Values=shbexpert" \
                      "Name=instance-state-name,Values=running" \
            --query 'Reservations[0].Instances[0].InstanceId' --output text)
          [ "$INSTANCE_ID" != "None" ] || { echo "Không tìm thấy instance"; exit 1; }
          echo "INSTANCE_ID=$INSTANCE_ID" >> "$GITHUB_ENV"

          PUBLIC_IP=$(aws ec2 describe-addresses \
            --filters "Name=tag:Name,Values=shbexpert-eip" \
            --query 'Addresses[0].PublicIp' --output text)
          echo "APP_DOMAIN=app.${PUBLIC_IP//./-}.sslip.io" >> "$GITHUB_ENV"

      - name: Upload config tarball
        run: |
          set -euo pipefail
          tar -czf /tmp/deploy.tar.gz \
            docker-compose.yml docker-compose.prod.yml deploy/ postgres/
          aws s3 cp /tmp/deploy.tar.gz \
            "s3://$DEPLOY_BUCKET/deploys/$IMAGE_TAG.tar.gz"

      - name: Run deploy over SSM
        run: |
          set -euo pipefail
          # AWS-RunShellScript không kế thừa env của runner — mọi biến
          # phải inline vào commands. IMAGE_TAG đặc biệt quan trọng: VM
          # không có cách nào suy ra git SHA.
          #
          # Dùng jq sinh JSON thay vì escape tay: chuỗi lệnh phải đi qua
          # ba lớp (YAML → bash → JSON), escape thủ công ở đó là nguồn
          # lỗi khó chẩn đoán nhất của cả workflow. jq đảm bảo JSON hợp
          # lệ, và jq có sẵn trên ubuntu-latest.
          jq -n \
            --arg bucket "$DEPLOY_BUCKET" \
            --arg tag "$IMAGE_TAG" \
            --arg region "${{ vars.AWS_REGION }}" \
            --arg registry "$ECR_REGISTRY" \
            '{
               commands: [
                 "set -euo pipefail",
                 "aws s3 cp s3://\($bucket)/deploys/\($tag).tar.gz /tmp/deploy.tar.gz",
                 "tar -xf /tmp/deploy.tar.gz -C /opt/shbexpert",
                 "rm /tmp/deploy.tar.gz",
                 "cd /opt/shbexpert && AWS_REGION=\($region) ECR_REGISTRY=\($registry) IMAGE_TAG=\($tag) bash deploy/deploy.sh"
               ]
             }' > /tmp/ssm-params.json

          cat /tmp/ssm-params.json   # để log có bản ghi lệnh đã gửi

          CMD_ID=$(aws ssm send-command \
            --document-name AWS-RunShellScript \
            --instance-ids "$INSTANCE_ID" \
            --comment "deploy $IMAGE_TAG" \
            --parameters file:///tmp/ssm-params.json \
            --query 'Command.CommandId' --output text)
          echo "SSM command: $CMD_ID"

          for _ in $(seq 1 120); do
            STATUS=$(aws ssm get-command-invocation \
              --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
              --query 'Status' --output text 2>/dev/null || echo Pending)
            case "$STATUS" in
              Success) break ;;
              Failed|Cancelled|TimedOut) ;;
              *) sleep 10; continue ;;
            esac
            break
          done

          aws ssm get-command-invocation \
            --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
            --query 'StandardOutputContent' --output text

          if [ "$STATUS" != "Success" ]; then
            echo "::error::Deploy thất bại ($STATUS)"
            aws ssm get-command-invocation \
              --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
              --query 'StandardErrorContent' --output text
            exit 1
          fi

      - name: Verify site is live
        run: |
          set -euo pipefail
          for _ in $(seq 1 30); do
            CODE=$(curl -s -o /dev/null -w '%{http_code}' "https://$APP_DOMAIN/" || echo 000)
            if [ "$CODE" = "200" ]; then
              echo "Site khoẻ: https://$APP_DOMAIN/"
              exit 0
            fi
            sleep 10
          done
          echo "::error::Site không phản hồi 200 sau 5 phút"
          exit 1
```

- [ ] **Step 3: Commit và merge lên `main`**

```bash
git add .github/workflows/deploy.yml
git commit -m "feat(ci): workflow deploy tự động lên VM qua ECR + S3 + SSM"
git push
gh pr create --base main --title "feat: CI/CD pipeline" \
  --body "Xem docs/superpowers/specs/2026-07-18-cicd-github-actions-design.md"
```

Merge PR sau khi CI xanh.

- [ ] **Step 4: Theo dõi lần deploy đầu tiên**

```bash
gh run watch
```

Lần đầu chậm hơn hẳn: cache buildx rỗng và VM phải kéo toàn bộ 8 ảnh mới.

Nếu fail, đọc theo thứ tự: `Discover infra` (tag chưa apply?) → `Run deploy over SSM` (output của `deploy.sh` được in ra) → `Verify site is live` (Caddy chưa xin được chứng chỉ?).

**Đường lui:** `rsync` vẫn dùng được cho tới khi workflow chạy ổn.

- [ ] **Step 5: Xác minh rollback thật sự hoạt động**

Đây là bước dễ bị bỏ qua nhất và cũng là bước duy nhất chứng minh nhánh logic ở Step 2 đúng:

```bash
git log --format='%H' -n 2 main   # lấy SHA áp chót
gh workflow run deploy.yml -f image_tag=<SHA_CŨ>
gh run watch
```

Expected:
- Job `build-push` hiện **skipped**
- Job `deploy` vẫn **chạy** — nếu nó cũng skip thì điều kiện `if: always()` sai
- Log in `Deploying tag: <SHA_CŨ>`
- `Verify site is live` pass

Rồi deploy lại về HEAD:

```bash
gh workflow run deploy.yml -f image_tag=$(git rev-parse main)
```

- [ ] **Step 6: Cập nhật README**

Thêm mục "Deploy" vào `README.md`: merge `main` để deploy; `gh workflow run deploy.yml -f image_tag=<sha>` để rollback; giới hạn rollback ~10 lần deploy do ECR lifecycle policy.

```bash
git add README.md
git commit -m "docs: hướng dẫn deploy và rollback"
```

---

## Self-Review

**Spec coverage:**

| Spec | Task |
|---|---|
| §1 kênh S3+SSM chưa chạy | Task 1 |
| §4 compose `image:` | Task 5 |
| §5 `ecr.tf` + quyền pull VM | Task 3 |
| §5 `github_oidc.tf` | Task 4 |
| §5 `compute.tf` tag merge | Task 4 Step 1 |
| §5 `user_data.sh` awscli | Task 1 Step 6 |
| §6 `deploy.sh` pull | Task 6 |
| §7 runtime discovery, 2 vars | Task 7 Steps 1-2 |
| §8 tag SHA + rollback | Task 7 Step 5 |
| §9 ci.yml | Task 2 |
| §9 deploy.yml, phân chia trách nhiệm, nhánh trigger, concurrency | Task 7 |
| §10 chỗ chừa cho dự án B | Task 2 Step 3 (job `test`) |
| §12 việc làm tay | Task 1, Task 7 Step 1 |

Không có mục spec nào thiếu task.

**Điểm chưa chắc chắn, cần xác minh lúc chạy:**

1. **Thumbprint OIDC** (Task 4) — AWS không còn xác thực giá trị này từ 2023, nhưng provider `~> 5.0` vẫn đòi trường non-empty. Nếu apply lỗi, thử bỏ `thumbprint_list`.
2. **Push lại cùng SHA lên tag IMMUTABLE** (Task 3) — hành vi của ECR khi digest không đổi là chỗ chưa rõ. Đường lui: commit rỗng để có SHA mới.
3. **Số lượng resource trong `terraform plan`** (Task 3 Step 2) — đọc kỹ plan thật trước khi apply, đừng tin con số trong tài liệu này.

**Rủi ro đã loại bỏ, không còn cần xác minh:**

- ~~Escape `--parameters commands=[...]` qua ba lớp YAML/bash/JSON~~ — đã thay bằng `jq -n` sinh file JSON rồi truyền `--parameters file://`. Đây từng là điểm dễ vỡ nhất của plan; thay cơ chế tốt hơn là thêm bước test cho cơ chế dễ vỡ.
