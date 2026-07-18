variable "region" {
  description = "Parent AWS region for the Hanoi Local Zone."
  type        = string
  default     = "ap-southeast-1"
}

variable "local_zone" {
  description = "Hanoi Local Zone name where the VM lives."
  type        = string
  default     = "ap-southeast-1-han-1a"
}

variable "az_group" {
  description = "Zone group to opt into, and the network border group used by the Elastic IP (note: NOT the -1a zone name)."
  type        = string
  default     = "ap-southeast-1-han-1"
}

variable "instance_type" {
  description = "Hanoi LZ only offers C7i/M7i/R7i families. m7i.xlarge = 4 vCPU / 16 GB."
  type        = string
  default     = "m7i.xlarge"
}

variable "ami" {
  description = "Ubuntu 24.04 LTS amd64 (region-wide AMI, usable in the Local Zone)."
  type        = string
  default     = "ami-0ed6a65b84536f6ce"
}

variable "subnet_cidr" {
  description = "Free /20 in the default VPC (172.31.0/16; .0/.16/.32 already taken)."
  type        = string
  default     = "172.31.48.0/20"
}

variable "ssh_allow_cidr" {
  description = "CIDR allowed to reach port 22. Defaults to the operator's current IP."
  type        = string
  default     = "14.191.163.118/32"
}

variable "ssh_public_key" {
  description = "OpenSSH public key installed on the VM (private key stays off-repo)."
  type        = string
  default     = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFwtpcrBrposmro6mDVv88dpCJPBPF/0WybLUMjj9EQY shbexpert-deploy"
}

variable "root_volume_gb" {
  description = "Root EBS gp3 size — enough for 12 container images + volumes."
  type        = number
  default     = 40
}

variable "project" {
  description = "Name/tag prefix."
  type        = string
  default     = "shbexpert"
}
