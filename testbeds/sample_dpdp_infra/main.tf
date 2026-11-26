# ARGUS Sample Non-DPDP Terraform Workspace (Safe Local Demo Target)
# Contains intentional DPDP Act 2023 & CIS AWS misconfigurations for local scanning.

variable "region" {
  default = "ap-south-1"
}

variable "bucket_name" {
  default = "swasthya-demo-citizen-kyc-pii"
}

resource "aws_s3_bucket" "citizen_kyc" {
  bucket = var.bucket_name
  region = var.region
  tags = {
    contains_personal_data = "true"
    environment            = "demo"
  }
}

resource "aws_security_group" "bastion" {
  name   = "swasthya-bastion-sg"
  vpc_id = "vpc-0a1b2c3d"
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_user" "dev" {
  name = "developer-raynor"
}

resource "aws_iam_access_key" "dev_key" {
  user   = aws_iam_user.dev.name
  status = "Active"
}

resource "aws_iam_role" "app_role" {
  name = "app-deployer-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = "arn:aws:iam::local:user/developer-raynor" }
    }]
  })
}

resource "aws_iam_policy" "admin_pol" {
  name = "dev-admin-wildcard"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "AllowAll"
      Effect   = "Allow"
      Action   = ["*"]
      Resource = ["*"]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "attach_admin" {
  role       = aws_iam_role.app_role.name
  policy_arn = aws_iam_policy.admin_pol.arn
}

resource "aws_db_instance" "citizen_pg" {
  identifier        = "swasthya-citizen-db"
  storage_encrypted = false
  availability_zone = "ap-south-1a"
}

resource "aws_cloudtrail" "audit_trail" {
  name           = "swasthya-trail"
  enable_logging = false
}
