terraform {
  required_version = ">= 1.6.0"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.33"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.16"
    }
  }
}

provider "kubernetes" {
  config_path = var.kubeconfig
}

provider "helm" {
  kubernetes {
    config_path = var.kubeconfig
  }
}

resource "kubernetes_namespace" "metaswap" {
  metadata {
    name = "metaswap"
  }
}

resource "helm_release" "metaswap" {
  name       = "metaswap-v3"
  namespace  = kubernetes_namespace.metaswap.metadata[0].name
  chart      = "${path.module}/../helm/metaswap-v3"
  values     = [file("${path.module}/values-production.yaml")]
  depends_on = [kubernetes_namespace.metaswap]
}
