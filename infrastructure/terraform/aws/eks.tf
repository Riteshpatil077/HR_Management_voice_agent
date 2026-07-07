# ============================================================================
# Terraform — Amazon EKS Cluster
# Production-grade: managed node groups, IRSA, Karpenter, add-ons
# ============================================================================

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.6"

  name = "hr-voice-agent-vpc"
  cidr = var.vpc_cidr

  azs             = slice(data.aws_availability_zones.available.names, 0, 3)
  private_subnets = var.private_subnet_cidrs
  public_subnets  = var.public_subnet_cidrs

  enable_nat_gateway     = true
  single_nat_gateway     = false   # HA: one per AZ
  enable_dns_hostnames   = true
  enable_dns_support     = true

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
    "karpenter.sh/discovery"           = "hr-voice-agent"
  }
  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.8"

  cluster_name    = "hr-voice-agent-${var.environment}"
  cluster_version = "1.30"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # -- Cluster Access -------------------------------------------------------
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true
  cluster_endpoint_public_access_cidrs = var.cluster_api_access_cidrs

  # -- Encryption -----------------------------------------------------------
  cluster_encryption_config = {
    resources = ["secrets"]
    provider_key_arn = aws_kms_key.eks.arn
  }

  # -- Logging --------------------------------------------------------------
  cluster_enabled_log_types = [
    "api", "audit", "authenticator", "controllerManager", "scheduler"
  ]

  # -- Managed Node Groups --------------------------------------------------
  eks_managed_node_groups = {
    # General purpose nodes for most services
    general = {
      instance_types = ["m6i.xlarge"]
      min_size       = 3
      max_size       = 20
      desired_size   = 6
      
      disk_size = 100
      
      labels = {
        role = "general"
      }
      
      taints = []
      
      update_config = {
        max_unavailable_percentage = 25
      }
    }

    # CPU-optimized for voice processing workers
    voice_processing = {
      instance_types = ["c6i.2xlarge", "c6i.4xlarge"]
      min_size       = 2
      max_size       = 30
      desired_size   = 3
      
      disk_size = 50
      
      labels = {
        role = "voice-processing"
      }
      
      taints = [
        {
          key    = "workload"
          value  = "voice"
          effect = "NO_SCHEDULE"
        }
      ]
    }
  }

  # -- EKS Add-ons ----------------------------------------------------------
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    vpc-cni = {
      most_recent    = true
      before_compute = true
    }
    kube-proxy = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = module.ebs_csi_irsa_role.iam_role_arn
    }
  }

  # -- OIDC for IRSA --------------------------------------------------------
  enable_irsa = true
}

# -- EBS CSI IRSA Role --------------------------------------------------------
module "ebs_csi_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.37"

  role_name             = "ebs-csi-${var.environment}"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }
}

# -- Karpenter Node IAM (for cluster autoscaling) ----------------------------
module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 20.8"

  cluster_name          = module.eks.cluster_name
  irsa_oidc_provider_arn = module.eks.oidc_provider_arn
  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }
}
