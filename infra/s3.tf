# Private bucket used purely as a transfer channel for deploy artifacts
# (tarball of the repo). The VM pulls from here via SSM using its instance
# role — no SSH, no GitHub token on the box. Safe to empty/destroy anytime.
resource "aws_s3_bucket" "deploy" {
  bucket        = "${var.project}-deploy-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_public_access_block" "deploy" {
  bucket                  = aws_s3_bucket.deploy.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Let the VM's SSM role read deploy artifacts from this bucket only.
resource "aws_iam_role_policy" "ssm_s3_read" {
  name = "${var.project}-deploy-s3-read"
  role = aws_iam_role.ssm.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:ListBucket"]
      Resource = [aws_s3_bucket.deploy.arn, "${aws_s3_bucket.deploy.arn}/*"]
    }]
  })
}

output "deploy_bucket" {
  value = aws_s3_bucket.deploy.bucket
}
