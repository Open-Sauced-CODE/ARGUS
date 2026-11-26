"""ARGUS Neo4j Attack Graph Seeder & Visualizer
Connects to Neo4j, seeds the Phase II Cartography & Derived Attack Graph,
and outputs high-impact Cypher queries for the evaluator demonstration.

Usage:
    python seed_neo4j.py
    python seed_neo4j.py --clear
"""

from __future__ import annotations

import argparse
import os
import sys
from neo4j import GraphDatabase

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Argus1234")


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def clear_graph(session):
    print("Clearing existing ARGUS demo nodes...")
    session.run("MATCH (n) WHERE n.argus_demo = true OR n:ARGUS_Demo DETACH DELETE n")


def seed_graph(session):
    print("Seeding ARGUS Cloud Topology & Attack Graph...")

    cypher_nodes = """
    // 1. AWS Account & VPC
    MERGE (acc:AWSAccount:ARGUS_Demo {id: '123456789012', name: 'ARGUS-Enterprise-Prod', argus_demo: true})
    MERGE (vpc:AWSVpc:VirtualNetwork:ARGUS_Demo {id: 'vpc-01a2b3c4d5', name: 'Prod-VPC-Mumbai', region: 'ap-south-1', argus_demo: true})
    MERGE (subnet:AWSEC2Subnet:Subnet:ARGUS_Demo {id: 'subnet-public-1', name: 'ap-south-1a-public-subnet', argus_demo: true})
    
    // 2. Network Exposure & Security Group
    MERGE (internet:AWSIpRange:IpRange:AttackerEntry:ARGUS_Demo {id: '0.0.0.0/0', range: '0.0.0.0/0', label: 'Public Internet (Attacker Source)', argus_demo: true})
    MERGE (rule:AWSIpPermissionInbound:IpPermissionInbound:ARGUS_Demo {id: 'rule-ssh-inbound', fromport: 22, toport: 22, protocol: 'tcp', argus_demo: true})
    MERGE (sg:AWSEC2SecurityGroup:EC2SecurityGroup:ARGUS_Demo {id: 'sg-web-public', groupid: 'sg-0a1b2c3d4e', name: 'Public-Web-SecurityGroup', argus_demo: true})
    
    // 3. Compromised IAM User & Access Key
    MERGE (user:AWSPrincipal:AWSUser:UserAccount:ARGUS_Demo {
        id: 'arn:aws:iam::123456789012:user/raynor-cgidjq6epnjtgc', 
        name: 'raynor-cgidjq6epnjtgc', 
        compromised: true, 
        role_type: 'developer', 
        argus_demo: true
    })
    MERGE (key:AWSAccountAccessKey:AccountAccessKey:ARGUS_Demo {
        id: 'AKIAIOSFODNN7EXAMPLE', 
        accesskeyid: 'AKIAIOSFODNN7EXAMPLE', 
        status: 'Active', 
        leak_source: 'GitHub Public Repo', 
        argus_demo: true
    })
    
    // 4. Over-permissive IAM Policy & Statement (Privilege Escalation vector)
    MERGE (pol:AWSPolicy:AWSManagedPolicy:ARGUS_Demo {
        id: 'arn:aws:iam::123456789012:policy/cg-raynor-policy', 
        name: 'cg-raynor-policy', 
        argus_demo: true
    })
    MERGE (stmt:AWSPolicyStatement:ARGUS_Demo {
        id: 'stmt-allow-create-policy', 
        sid: 'AllowPolicyVersionEscalation', 
        effect: 'Allow', 
        action: 'iam:CreatePolicyVersion', 
        resource: '*', 
        vuln: 'Privilege Escalation to Admin', 
        argus_demo: true
    })

    // 5. High-Privilege Role
    MERGE (role:AWSPrincipal:AWSRole:PermissionRole:ARGUS_Demo {
        id: 'arn:aws:iam::123456789012:role/argus-data-pipeline-role', 
        name: 'argus-data-pipeline-role', 
        trusted_services: ['ec2.amazonaws.com'], 
        argus_demo: true
    })

    // 6. Target Crown Jewels (S3 Buckets with PII & Misconfigurations)
    MERGE (b1:AWSS3Bucket:CrownJewel:ARGUS_Demo {
        id: 'arn:aws:s3:::indian-citizen-medical-records-store', 
        name: 'indian-citizen-medical-records-store', 
        default_encryption: false, 
        block_public_acls: false, 
        block_public_policy: false, 
        rule_violation: 'India DPDP Act 2023 Rule 6', 
        argus_demo: true
    })
    MERGE (b2:AWSS3Bucket:CrownJewel:ARGUS_Demo {
        id: 'arn:aws:s3:::production-finance-ledger-2026', 
        name: 'production-finance-ledger-2026', 
        default_encryption: false, 
        rule_violation: 'CIS AWS Benchmark 2.1.1', 
        argus_demo: true
    })

    // 7. Compliance Tags
    MERGE (t1:AWSTag:ARGUS_Demo {id: 'tag-dpdp', key: 'contains_personal_data', value: 'true', argus_demo: true})
    MERGE (t2:AWSTag:ARGUS_Demo {id: 'tag-env', key: 'environment', value: 'production', argus_demo: true})

    // 8. Full Admin Target
    MERGE (admin:ADMIN_EQUIV:CrownJewel:ARGUS_Demo {
        id: 'ADMIN_EQUIV', 
        name: 'Full AWS Cloud Administrator Access', 
        impact: 'Full Account Compromise', 
        argus_demo: true
    })
    """
    session.run(cypher_nodes)

    cypher_relationships = """
    MATCH (acc:AWSAccount {id: '123456789012'}),
          (vpc:AWSVpc {id: 'vpc-01a2b3c4d5'}),
          (subnet:AWSEC2Subnet {id: 'subnet-public-1'}),
          (internet:AWSIpRange {id: '0.0.0.0/0'}),
          (rule:AWSIpPermissionInbound {id: 'rule-ssh-inbound'}),
          (sg:AWSEC2SecurityGroup {id: 'sg-web-public'}),
          (user:AWSUser {id: 'arn:aws:iam::123456789012:user/raynor-cgidjq6epnjtgc'}),
          (key:AWSAccountAccessKey {id: 'AKIAIOSFODNN7EXAMPLE'}),
          (pol:AWSPolicy {id: 'arn:aws:iam::123456789012:policy/cg-raynor-policy'}),
          (stmt:AWSPolicyStatement {id: 'stmt-allow-create-policy'}),
          (role:AWSRole {id: 'arn:aws:iam::123456789012:role/argus-data-pipeline-role'}),
          (b1:AWSS3Bucket {id: 'arn:aws:s3:::indian-citizen-medical-records-store'}),
          (b2:AWSS3Bucket {id: 'arn:aws:s3:::production-finance-ledger-2026'}),
          (t1:AWSTag {id: 'tag-dpdp'}),
          (t2:AWSTag {id: 'tag-env'}),
          (admin:ADMIN_EQUIV {id: 'ADMIN_EQUIV'})

    // Ingestion Topology Edges (Cartography)
    MERGE (vpc)-[:RESOURCE {argus_demo: true}]->(acc)
    MERGE (subnet)-[:PART_OF_SUBNET {argus_demo: true}]->(vpc)
    MERGE (internet)-[:MEMBER_OF_IP_RULE {argus_demo: true}]->(rule)
    MERGE (rule)-[:MEMBER_OF_EC2_SECURITY_GROUP {argus_demo: true}]->(sg)
    MERGE (user)-[:AWS_ACCESS_KEY {argus_demo: true}]->(key)
    MERGE (user)-[:POLICY {argus_demo: true}]->(pol)
    MERGE (pol)-[:STATEMENT {argus_demo: true}]->(stmt)
    MERGE (role)-[:TRUSTS_AWS_PRINCIPAL {argus_demo: true}]->(user)
    MERGE (b1)-[:TAGGED {argus_demo: true}]->(t1)
    MERGE (b1)-[:TAGGED {argus_demo: true}]->(t2)
    MERGE (b2)-[:TAGGED {argus_demo: true}]->(t2)

    // Derived Attack Graph Hacker-Movement Edges
    MERGE (internet)-[:USES_KEY {p: 0.90, etype: 'USES_KEY', argus_demo: true}]->(user)
    MERGE (internet)-[:EXPOSES_PORT {p: 0.85, port: 22, etype: 'NET_INBOUND', argus_demo: true}]->(sg)
    MERGE (user)-[:CAN_ASSUME {p: 0.80, etype: 'CAN_ASSUME', argus_demo: true}]->(role)
    MERGE (user)-[:CAN_ESCALATE {p: 0.92, etype: 'CAN_ESCALATE', via: 'iam:CreatePolicyVersion', argus_demo: true}]->(admin)
    MERGE (role)-[:CAN_ACCESS {p: 0.88, etype: 'CAN_ACCESS', personal_data: true, argus_demo: true}]->(b1)
    MERGE (role)-[:CAN_ACCESS {p: 0.75, etype: 'CAN_ACCESS', argus_demo: true}]->(b2)
    MERGE (user)-[:CAN_ACCESS {p: 0.65, etype: 'CAN_ACCESS', argus_demo: true}]->(b2)
    """
    session.run(cypher_relationships)
    print("SUCCESS: Demo Attack Graph Seeded Successfully!")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    with get_driver() as driver:
        with driver.session() as session:
            clear_graph(session)
            if not args.clear:
                seed_graph(session)


if __name__ == "__main__":
    main()

