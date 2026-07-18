# CI/CD GitHub Actions — Design

**Ngày:** 2026-07-18
**Trạng thái:** Đã chốt, chờ implement
**Phạm vi:** Chỉ pipeline CI/CD (dự án A). Test/eval infrastructure (B) và Langfuse observability (C) tách thành spec riêng.

## 1. Bối cảnh

Deploy hiện tại là thủ công qua **rsync**: đẩy source trực tiếp vào `/opt/shbexpert` trên VM, rồi chạy `deploy/deploy.sh` → `docker compose up -d --build`. VM (`m7i.xlarge`, 4 vCPU / 16 GB / 40 GB disk) tự build cả 8 service ứng dụng mỗi lần deploy.

Commit `56e67f0` ("thêm SSM access + S3 deploy channel") đã dựng sẵn **hạ tầng** cho một kênh deploy khác — bucket S3, IAM role SSM, instance profile — nhưng chỉ đụng `compute.tf`/`iam.tf`/`s3.tf`, không thêm script nào đọc khe đó. Toàn repo không có một tham chiếu nào tới `aws s3`, `aws ssm`, hay `awscli`; `user_data.sh:3` ghi rõ *"Code is shipped separately (rsync) since we deploy manually without CI/CD"*.

**Kênh S3+SSM do đó chưa từng chạy.** Spec này kế thừa hạ tầng đã có và viết phần code còn thiếu để nó chạy lần đầu — không phải migrate một cơ chế đang vận hành.

Bốn vấn đề:

- Deploy chậm và downtime dài — build 8 image trên một VM cũng đang chạy production.
- Không rollback được — không có artifact nào được đánh version.
- Deploy phụ thuộc máy cá nhân — `rsync` chạy từ laptop của người deploy, không tái lập được, không có log.
- Không có quality gate — repo hiện không có test, không có config linter Python, không có `.github/`.

## 2. Quyết định đã chốt

| Câu hỏi | Lựa chọn |
|---|---|
| Phạm vi | CI + CD tự động deploy |
| Nơi build image | GitHub Actions → push ECR |
| Trigger deploy | Merge vào `main` → auto deploy, không cần phê duyệt |
| Quality gate | Ruff + tsc/next lint + docker build + pytest scaffold |
| Quản lý config | Runtime discovery, chỉ lưu 2 repo vars |
| Eval AI / Langfuse | Hoãn sang spec B và C |

## 3. Kiến trúc

Artifact đi qua ECR, config đi qua S3. Hai kênh tách biệt.

```
PR ─────────► ci.yml
              ruff · next lint + tsc · docker build (no push) · pytest(LLM_MOCK=true)
              └─ không dùng credential AWS nào

push main ──► deploy.yml
              ├─ build-push: matrix 8 service ──► ECR, tag = git SHA
              └─ deploy:    tarball config ──► S3 ──► SSM ──► deploy.sh
                                                              └─ pull · up -d · alembic · seed
```

PR không chạm AWS — chỉ build để xác minh Dockerfile còn hợp lệ. Quyền đẩy ECR và deploy bị siết bằng điều kiện OIDC trên `ref:refs/heads/main`, nên PR từ fork không thể lấy được credential.

## 4. Thay đổi `docker-compose.yml`

8 service ứng dụng (`api`, `worker`, `web`, `tools-mock`, `mcp-deterministic`, `mcp-rag`, `mcp-external`, `mcp-state`) hiện chỉ có `build:`. Thêm `image:` song song:

```yaml
  api:
    image: ${REGISTRY:-shbexpert}/shbexpert/api:${IMAGE_TAG:-dev}
    build:
      context: .
      dockerfile: api/Dockerfile
```

Giữ cả hai key là có chủ đích:

- **Dev local**: `docker compose up` vẫn build như cũ. Compose chỉ build khi image chưa tồn tại local; nó không tự pull từ remote với service có `build:`.
- **Prod**: `docker compose pull` kéo đúng SHA từ ECR, rồi `up -d --no-build`.

Một file compose phục vụ cả hai môi trường — không phải duy trì hai bản lệch nhau.

Phần `shbexpert/` thứ hai là **tên repository trên ECR** (`${var.project}/<service>`), không phải lặp thừa — đường dẫn đầy đủ lúc chạy là `<account>.dkr.ecr.<region>.amazonaws.com/shbexpert/api:<sha>`.

Default `shbexpert/shbexpert/api:dev` là namespace **không tồn tại trên Docker Hub** — đây là chủ ý. Nếu ai đó chạy `docker compose pull` ngoài môi trường prod, lệnh fail ngay với `pull access denied` thay vì âm thầm kéo nhầm image. Rủi ro còn lại rất hẹp: một dev vừa deploy xong, còn `REGISTRY`/`IMAGE_TAG` sót trong shell, rồi `pull` ở repo local — phải `unset` trước.

`postgres`, `redis`, `qdrant`, `minio` giữ nguyên (image public).

## 5. Terraform bổ sung

Apply thủ công — spec này không tạo workflow cho Terraform.

### `infra/ecr.tf` (mới)

8 repository qua `for_each`, kèm lifecycle policy giữ 10 image gần nhất. Không có policy này thì ECR phình vô hạn và trả tiền cho image chết.

Tên resource dùng xuyên suốt spec:

```hcl
locals {
  services = toset([
    "api", "worker", "web", "tools-mock",
    "mcp-deterministic", "mcp-rag", "mcp-external", "mcp-state",
  ])
}

resource "aws_ecr_repository" "app" {
  for_each = local.services
  name     = "${var.project}/${each.key}"
}
```

**File này cũng phải cấp quyền kéo image cho VM.** Role SSM hiện tại (`iam.tf` + `s3.tf`) chỉ có `AmazonSSMManagedInstanceCore` và `s3:GetObject/ListBucket` — **không có quyền ECR nào**. Thiếu policy dưới đây thì `docker compose pull` trên VM trả 401 và toàn bộ thiết kế này không chạy được:

```hcl
resource "aws_iam_role_policy" "ssm_ecr_pull" {
  role = aws_iam_role.ssm.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # GetAuthorizationToken không hỗ trợ resource-level permission
      { Effect = "Allow", Action = "ecr:GetAuthorizationToken", Resource = "*" },
      {
        Effect   = "Allow"
        Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
        Resource = [for r in aws_ecr_repository.app : r.arn]
      }
    ]
  })
}
```

### `infra/github_oidc.tf` (mới)

- `aws_iam_openid_connect_provider` cho `token.actions.githubusercontent.com`
- Role với trust policy khoá theo `repo:TruongSon421/dashmint_ai:ref:refs/heads/main`
- Quyền tối thiểu:
  - push ECR (8 repository)
  - `s3:PutObject` vào bucket deploy
  - push ECR — phải liệt kê đủ action, thiếu một cái là fail giữa chừng sau khi đã upload layer:
    ```
    ecr:GetAuthorizationToken            (Resource = "*")
    ecr:BatchCheckLayerAvailability
    ecr:InitiateLayerUpload
    ecr:UploadLayerPart
    ecr:CompleteLayerUpload
    ecr:PutImage                          (Resource = 8 repository ARN)
    ```
  - `ssm:SendCommand` — cần **cả hai** resource ARN trong cùng statement: document `arn:aws:ssm:*:*:document/AWS-RunShellScript` và instance `arn:aws:ec2:*:*:instance/*` giới hạn bằng condition trên tag `Project=shbexpert`
  - `ssm:GetCommandInvocation` trên `arn:aws:ssm:*:*:command/*` — **bắt buộc**, vì `SendCommand` chỉ trả `CommandId`; không có quyền này thì §9 không đọc được exit code và sẽ báo deploy thành công kể cả khi `deploy.sh` chết
  - `ec2:DescribeInstances`, `ec2:DescribeAddresses` cho bước discovery ở §7

Không có access key tĩnh nào tồn tại trong hệ thống.

### `infra/compute.tf` (sửa)

Instance đã có `tags = { Name = "${var.project}-vm" }` tại dòng 20. Terraform thay **nguyên khối** map tags, nên phải merge chứ không ghi đè — mất tag `Name` sẽ khiến instance mất tên trong console và gãy mọi công cụ ops tham chiếu theo tên:

```hcl
  tags = {
    Name    = "${var.project}-vm"
    Project = var.project
    Role    = "app"
  }
```

Tag `Project` là cơ sở để workflow tìm ra instance lúc chạy (xem §7). Cập nhật tag là thao tác in-place — không recreate instance, không downtime.

EIP đã có sẵn `Name = "${var.project}-eip"` (dòng 28), dùng luôn cho việc discover `APP_DOMAIN` — không cần thêm tag.

### `infra/user_data.sh` (sửa)

Hiện chỉ cài `ca-certificates curl rsync git` + Docker — **không có AWS CLI**. VM cần nó để đăng nhập ECR (`aws ecr get-login-password | docker login`) và để kéo tarball config từ S3. Thêm bước cài `awscli`.

**Chốt phương án xác thực ECR: `docker login` mỗi lần deploy** (đúng như snippet §6). Token ECR hết hạn sau 12 giờ, nhưng điều đó không gây vấn đề vì `deploy.sh` đăng nhập lại ở đầu mỗi lần chạy. Nếu sau này muốn bỏ hẳn bước login khỏi `deploy.sh`, có thể chuyển sang `amazon-ecr-credential-helper` với `credHelpers` trong `~/.docker/config.json` — nằm ngoài phạm vi spec này.

Sửa `user_data.sh` cũng ghi rõ lại comment ở dòng 3, vì câu *"we deploy manually without CI/CD"* sẽ không còn đúng.

`infra/iam.tf` giữ nguyên — quyền ECR mới gắn vào role SSM qua `ecr.tf`, quyền của GitHub nằm ở role riêng trong `github_oidc.tf`.

## 6. Thay đổi `deploy/deploy.sh`

`deploy.sh` giả định tarball **đã được kéo về và giải nén** — việc đó do lệnh SSM làm, không phải nó (xem bảng phân chia trách nhiệm ở §9). Script này không chứa lệnh `aws s3` nào.

**Bắt buộc giữ biến `$COMPOSE` với cả hai file `-f`.** Overlay `docker-compose.prod.yml` là nơi khai báo Caddy — service duy nhất hướng ra internet (80/443) và là nơi nhận `APP_DOMAIN` để xin chứng chỉ TLS. Bỏ `-f docker-compose.prod.yml` thì Caddy không start: không TLS, không cổng nào mở ra ngoài (SG chỉ mở 80/443/22), và health check ở §9 fail dù stack nội bộ vẫn "healthy".

```bash
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

$COMPOSE pull                        # thay cho: up -d --build
$COMPOSE up -d --no-build
$COMPOSE run --rm api alembic upgrade head

# Seed giữ nguyên — các script đã idempotent
$COMPOSE run --rm mcp-rag python -m scripts.seed_policies
for c in c06 c07 c08; do
  $COMPOSE run --rm api python -m scripts.seed_case_"$c"
done
```

Tarball lên S3 chỉ còn config: `docker-compose.yml`, `docker-compose.prod.yml`, `deploy/Caddyfile`, `postgres/init/`. Không còn source code.

`scripts/` **không nằm trong tarball** vì đã được bake sẵn vào image: `api/Dockerfile:21` và `mcp-rag/Dockerfile:20` đều `COPY scripts/ /app/scripts/`. Ràng buộc đi kèm: `worker` và 3 service `mcp-*` còn lại **không** có `scripts/` trong image, nên mọi bước seed/migrate phải chạy qua `api` hoặc `mcp-rag`.

**Giải nén tarball không được xoá `.env`.** File `.env` production nằm ở `/opt/shbexpert/.env`, không có trong git và không có trong tarball. Dùng `tar -xf` ghi đè từng file — **tuyệt đối không** dùng `rsync --delete` hay xoá thư mục trước khi giải nén, vì như vậy sẽ thổi bay `.env` và toàn bộ stack mất secret. Named volume (`pg_data`, `qdrant_data`, `minio_data`) nằm ngoài thư mục nên an toàn.

VM không cần CPU để build nữa; thời gian deploy và downtime giảm mạnh.

## 7. Quản lý cấu hình — runtime discovery

**Nguyên tắc: chỉ lưu giá trị không thể suy ra được.**

Các giá trị như role ARN, bucket name, instance ID, registry URL đều là identifier công khai, không phải secret. Lưu chúng vào `secrets` còn phản tác dụng: GitHub mask chúng trong log, khiến deploy lỗi khó chẩn đoán. Dùng `vars`.

### Lưu trong repo vars (2 giá trị)

- `AWS_ROLE_ARN`
- `AWS_REGION`

Hai giá trị này bắt buộc phải lưu vì cần chúng để đăng nhập trước khi hỏi được AWS bất cứ điều gì.

### Discover lúc chạy (sau bước OIDC login)

```yaml
- name: Discover infra
  run: |
    ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    echo "ECR_REGISTRY=$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com" >> $GITHUB_ENV
    echo "DEPLOY_BUCKET=shbexpert-deploy-$ACCOUNT" >> $GITHUB_ENV

    INSTANCE_ID=$(aws ec2 describe-instances \
      --filters "Name=tag:Project,Values=shbexpert" \
                "Name=instance-state-name,Values=running" \
      --query 'Reservations[0].Instances[0].InstanceId' --output text)
    echo "INSTANCE_ID=$INSTANCE_ID" >> $GITHUB_ENV
```

`DEPLOY_BUCKET` dùng đúng công thức đặt tên trong `infra/s3.tf`: `${project}-deploy-${account_id}`.

**Vì sao không hardcode `INSTANCE_ID`:** đổi `var.ami` hoặc `var.instance_type` sẽ khiến Terraform replace instance → ID mới. Một biến cố định sẽ trỏ vào máy đã chết, và `ssm send-command` fail theo cách khó chẩn đoán. Lookup theo tag tự lành sau mọi lần recreate.

`.env` production vẫn nằm trên VM, không bao giờ đi qua git hay CI — giữ nguyên thiết kế sẵn có.

## 8. Chiến lược tag và rollback

Tag ảnh = **git SHA**, immutable. Không dùng `latest` cho production: `latest` khiến không xác định được VM đang chạy phiên bản nào và làm rollback bất khả thi.

**Rollback**: `workflow_dispatch` với input `image_tag` = SHA cũ. Vì tag immutable, rollback chỉ là pull lại image cũ — không rebuild, không phụ thuộc trạng thái git. Tarball config trên S3 cũng đặt key theo cùng SHA, nên rollback khôi phục đồng bộ cả image lẫn compose config (xem §9).

Ràng buộc: lifecycle policy giữ 10 image gần nhất, nên chỉ rollback được trong phạm vi ~10 lần deploy. Cần lùi xa hơn thì phải build lại từ commit cũ.

## 9. Workflows

### `.github/workflows/ci.yml`

Trigger: pull request, và push vào `develop`.

| Job | Nội dung |
|---|---|
| `lint-python` | Ruff (lint + format check) |
| `lint-web` | `next lint` + `tsc --noEmit` |
| `build` | Matrix 8 service, build không push, cache qua `type=gha` scope theo service |
| `test` | `pytest` với `LLM_MOCK=true` |

Cần thêm config Ruff vào `pyproject.toml` (hiện chưa có).

**Cảnh báo về giá trị thật của gate `lint-web`.** `web/Dockerfile` chạy `next dev` — chế độ development, hot reload — kể cả trên production; comment đầu file tự ghi *"Swap to a `next build` + `next start` multi-stage image later if a production deploy is actually needed."* Hệ quả: **không có bước `next build` nào tồn tại trong toàn bộ vòng đời**, nên CI không thể phát hiện lỗi build. `tsc --noEmit` bắt được lỗi kiểu, nhưng không bắt được lỗi chỉ lộ ra lúc Next.js build thật.

Có thể thêm `next build` vào CI để bắt lớp lỗi đó. Nhưng phải thành thật: khi đó CI đang kiểm chứng một artifact **không bao giờ được ship**, vì image runtime vẫn chạy `next dev`.

Đây là nợ kỹ thuật nằm ngoài phạm vi spec (xem §11), nhưng cần biết trước để không hiểu nhầm gate này mạnh hơn thực tế.

### `.github/workflows/deploy.yml`

Trigger: push vào `main`, và `workflow_dispatch` (input `image_tag` cho rollback).

| Job | Nội dung |
|---|---|
| `build-push` | Matrix 8 service → ECR, tag = git SHA |
| `deploy` | Discover infra → tarball config → S3 → `ssm send-command` chạy `deploy.sh` → poll health endpoint |

Job `deploy` phải chờ SSM command hoàn tất và kiểm tra exit code (`aws ssm get-command-invocation`, poll tới khi `Status` khác `InProgress`/`Pending`), sau đó poll `https://$APP_DOMAIN/` để xác nhận stack sống.

### Phân chia trách nhiệm: workflow vận chuyển, deploy.sh vận hành

Ranh giới này phải rõ, nếu không sẽ có bước không ai làm:

| Ai | Làm gì |
|---|---|
| Workflow (runner) | Đóng tarball, `aws s3 cp` lên `s3://$DEPLOY_BUCKET/deploys/<sha>.tar.gz` |
| Lệnh SSM (VM) | Kéo tarball về, giải nén vào `/opt/shbexpert`, rồi gọi `deploy.sh` |
| `deploy.sh` (VM) | Chỉ `login → pull → up → migrate → seed`. **Không** chứa `aws s3 cp` |

Lệnh SSM do đó phải gồm cả bước vận chuyển, không chỉ gọi `deploy.sh`:

```bash
aws s3 cp "s3://$DEPLOY_BUCKET/deploys/$IMAGE_TAG.tar.gz" /tmp/deploy.tar.gz \
  && tar -xf /tmp/deploy.tar.gz -C /opt/shbexpert \
  && rm /tmp/deploy.tar.gz \
  && cd /opt/shbexpert \
  && AWS_REGION=… ECR_REGISTRY=… IMAGE_TAG=… bash deploy/deploy.sh
```

Giữ `deploy.sh` không biết gì về S3 là có chủ đích: khi cần chạy lại bằng tay qua SSM session, chỉ việc gọi `deploy.sh` — không phải dựng lại tarball.

**Key tarball đặt theo SHA, trùng với tag image.** Điều này khiến rollback nhất quán: kéo `deploys/abc123.tar.gz` sẽ khôi phục đúng bộ `docker-compose.yml` + `Caddyfile` khớp với image `:abc123`. Nếu dùng key cố định kiểu `latest.tar.gz`, rollback sẽ ghép image cũ với config mới — một dạng hỏng rất khó chẩn đoán.

### Nhánh logic theo trigger

`build-push` chỉ có ý nghĩa khi deploy code mới. Khi rollback, image đã nằm sẵn trên ECR:

| Trigger | `build-push` | `IMAGE_TAG` |
|---|---|---|
| `push` vào `main` | chạy | `github.sha` |
| `workflow_dispatch` | skip — `if: github.event_name == 'push'` | `inputs.image_tag` |

**Cạm bẫy bắt buộc xử lý:** khi `build-push` bị skip, `needs: build-push` mặc định khiến job `deploy` **skip theo**. Rollback sẽ báo xanh mà không làm gì cả. Job `deploy` phải dùng:

```yaml
needs: build-push
if: always() && needs.build-push.result != 'failure'
```

Bỏ `build-push` khi rollback không chỉ để tiết kiệm. Nó không làm hỏng tag cũ (tag theo SHA là immutable, `github.sha` lúc dispatch là HEAD của `main` chứ không phải SHA muốn rollback về) — nhưng bắt chờ 8 lần build vô ích trong lúc production đang hỏng là thiệt hại thật.

`APP_DOMAIN` **không đọc được từ `infra/outputs.tf`** — Terraform output là khái niệm lúc apply, không tồn tại khi workflow chạy. Discover qua AWS API, nhất quán với §7. EIP đã có tag sẵn nên không cần thêm gì:

```yaml
- name: Discover app domain
  run: |
    PUBLIC_IP=$(aws ec2 describe-addresses \
      --filters "Name=tag:Name,Values=shbexpert-eip" \
      --query 'Addresses[0].PublicIp' --output text)
    echo "APP_DOMAIN=app.${PUBLIC_IP//./-}.sslip.io" >> $GITHUB_ENV
```

Công thức `app.<ip-dashed>.sslip.io` khớp với `infra/outputs.tf` — nếu công thức đó đổi, phải sửa cả hai chỗ.

### Truyền biến từ runner sang VM

`AWS_REGION`, `ECR_REGISTRY`, `IMAGE_TAG` được discover trên **runner**, nhưng `deploy.sh` chạy trên **VM** — hai môi trường tách rời. `AWS-RunShellScript` **không truyền env** của runner sang.

Chốt cách làm: **inline vào `commands` của lệnh SSM**. `deploy.sh` nhận chúng từ process env, không tự derive.

```yaml
aws ssm send-command \
  --document-name AWS-RunShellScript \
  --instance-ids "$INSTANCE_ID" \
  --parameters "commands=[\"cd /opt/shbexpert && AWS_REGION=$AWS_REGION ECR_REGISTRY=$ECR_REGISTRY IMAGE_TAG=$IMAGE_TAG bash deploy/deploy.sh\"]"
```

`IMAGE_TAG` **bắt buộc** phải đi đường này — nó là git SHA, VM không có cách nào suy ra. Nếu biến không tới nơi, compose rơi về default `:dev` và `pull` sẽ fail (tag đó không tồn tại trên ECR). Fail to là có chủ đích, nhưng đừng để nó xảy ra.

Không dùng file `.env.deploy` trong tarball: thêm một nguồn state có thể lệch, trong khi inline hiện nguyên trong lịch sử lệnh SSM — tiện truy vết. Ba giá trị này đều không phải secret.

### Chống deploy chồng nhau

Hai lần merge vào `main` sát nhau sẽ tạo hai workflow cùng chạy `deploy.sh` trên **một** VM — compose sẽ giẫm chân nhau giữa chừng. Bắt buộc có:

```yaml
concurrency:
  group: deploy-production
  cancel-in-progress: false
```

`cancel-in-progress: false` là có chủ đích — huỷ một lần deploy đang chạy dở nguy hiểm hơn là để nó chạy xong rồi mới chạy lần sau.

## 10. Chỗ chừa cho dự án B (test/eval)

Job `test` trong `ci.yml` chạy `pytest` với `LLM_MOCK=true` ngay từ đầu. Repo hiện chưa có test nào nên job pass rỗng.

Khi làm dự án B, chỉ cần thêm file vào `tests/` — **không phải sửa workflow**. Biến `LLM_MOCK=true` (đã có trong `.env.example`) đảm bảo CI không tốn token và không flaky.

CI **không chặn merge** khi job test rỗng.

## 11. Ngoài phạm vi

- **Dự án B — test/eval**: pytest scaffold thực, schema validation, retrieval hit-rate@k, DeepEval/Ragas trên golden case `c06`/`c07`/`c08`. Spec riêng.
- **Dự án C — Langfuse**: self-host cần thêm ~5-6 container (ClickHouse, Redis, Postgres riêng, blob storage, web, worker). VM hiện tại (16 GB RAM, 40 GB disk, đã chạy ~12 container) không đủ chỗ. Cần quyết định giữa Langfuse Cloud và nâng sizing. Spec riêng.
- **`web` chạy `next dev` trên production**: `web/Dockerfile` là image dev-mode (hot reload, không tối ưu, compile theo yêu cầu, tốn RAM, lộ source map). Trên VM 16 GB chia cho 12 container thì đây là chi phí thật. Chuyển sang multi-stage `next build` + `next start` là việc nên làm — chính comment trong Dockerfile đã hẹn — nhưng là thay đổi runtime, không phải CI/CD, nên tách riêng. Spec này cố ý **không** sửa nó: ECR vẫn build được image dev-mode bình thường, và trộn hai thay đổi vào một lần sẽ khiến lúc deploy hỏng không biết lỗi do đâu.
- **Terraform workflow**: `fmt`/`validate`/`plan` trên PR. Không thuộc phạm vi lần này; Terraform apply vẫn thủ công.
- **Môi trường staging**: chỉ có một VM. Cần VM thứ hai trước khi tách staging/production.

## 12. Việc phải làm tay sau khi implement

1. `terraform apply` để tạo ECR repos, OIDC provider, IAM role GitHub, cấp quyền ECR pull cho role SSM của VM, và merge tag `Project` vào instance. Tag update là in-place — không recreate, không downtime.
2. Tạo 2 repo variables trên GitHub: `AWS_ROLE_ARN`, `AWS_REGION`.
3. **Cài AWS CLI lên VM đang chạy.** Sửa `user_data.sh` chỉ có tác dụng với instance mới; VM hiện tại phải cài tay qua SSM session.
4. Deploy lần đầu sẽ pull image mới hoàn toàn — chậm hơn các lần sau.

### Việc đầu tiên của implementation plan

Kênh S3 + SSM chưa từng chạy (xem §1) — toàn bộ phần `aws s3 cp` + `ssm send-command` là **code mới**, không phải sửa code cũ.

Bước đầu tiên của plan phải là làm kênh đó thông end-to-end **bằng tay**: cài AWS CLI lên VM, đẩy thử một tarball lên S3, gửi một lệnh SSM kéo về và giải nén, đọc exit code. Chỉ khi bước này chạy được mới bắt đầu viết workflow — nếu không, mọi lỗi sau đó sẽ lẫn lộn giữa "workflow sai" và "kênh chưa bao giờ hoạt động".

Cho tới khi kênh mới được xác minh, `rsync` vẫn là đường deploy dự phòng.
