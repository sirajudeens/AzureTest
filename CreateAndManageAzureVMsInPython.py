import json
import logging
import argparse

from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.compute.models import DiskCreateOption

from azure.mgmt.resource.resources.models import *
from resource_manager import *

SUBSCRIPTION_ID = '490850fb-3d19-4a56-bd61-856dded531b1'
#SUBSCRIPTION_ID = '5393f919-a68a-43d0-9063-4b2bda6bffdf'
GROUP_NAME = 'sirajs-rg'
LOCATION = 'southcentralus'
VM_NAME = 'sirajsVM'

template_filename = "template-linux.json"
#template_filename = "template-linux-ext.json"
paramters_filename = "parameters.json"

LOGGER = logging.getLogger(__name__)

def get_credentials():
    credentials = ServicePrincipalCredentials(
        client_id = '228aeb17-c482-46a0-9e7d-a3880b23f73c',
        secret = 'OsPD/crrwY0W8Eflgw9yLFYLl3atWKrPla+iO0gzDDQ=',
        tenant = '72f988bf-86f1-41af-91ab-2d7cd011db47'
    )

    return credentials

def create_resource_group(resource_group_client):
    resource_group_params = { 'location':LOCATION }
    resource_group_result = resource_group_client.resource_groups.create_or_update(
        GROUP_NAME, 
        resource_group_params
    )

def deploy_vmss():
    with open(template_filename) as template_fh:
        template = json.load(template_fh)

    with open(paramters_filename) as parameters_fh:
        params = json.load(parameters_fh)

    props = DeploymentProperties(template=template,
                                 parameters=params,
                                 mode=DeploymentMode.incremental)
    poller = resource_group_client.deployments.create_or_update(GROUP_NAME, 'TestDeployment', props)
    poller.wait()


def parse_args(program):
    parser = argparse.ArgumentParser(prog=program)
    cmd_parsers = parser.add_subparsers(help="sub-command help", dest="command")

    create_test_profile_parser = cmd_parsers.add_parser("create-test-profile", help="Create test profiles by scenario")
    create_test_profile_parser.add_argument('--scenarios', help="scenarios to create tests for", required=True)
    create_test_profile_parser.add_argument("--config", help="environment configuration file", required=True)
    create_test_profile_parser.add_argument("--secrets", help="environment secrets configuration file", required=True)
    create_test_profile_parser.add_argument("--badge-sas", help="badge sas token", required=True)
    create_test_profile_parser.add_argument("--enable-live-debug", help="enable live debugging", required=True)
    create_test_profile_parser.add_argument("--jenkins-url", help="Jenkins url for this job", required=True)
    create_test_profile_parser.add_argument("--job-name", help="Jenkins job", required=True)

    start_test_parser = cmd_parsers.add_parser("start-testing", help="start testing")
    start_test_parser.add_argument('--test-profile-path', help="test config file path", required=True)
    start_test_parser.add_argument("--logfile", help="name of the log file, defaults to ./debug.log", required=False, default="debug.log")
    start_test_parser.add_argument("--log-saving-dir", help="directory to store harvested logs", required=True)
    start_test_parser.add_argument("--results-dir", help="directory to store test results", required=True)

    clean_up_parser = cmd_parsers.add_parser("clean-up", help="clean up resources used during tests")
    clean_up_parser.add_argument('--config', help="environment configuration file", required=True)
    clean_up_parser.add_argument('--secrets', help="environment secrets configuration file", required=True)
    clean_up_parser.add_argument('--rg-name-file', help="file containing resource group names to be cleaned up", required=True)
    clean_up_parser.add_argument("--logfile", help="name of the log file, defaults to ./debug.log", required=False, default="cleanup.log")
    args = parser.parse_args()
    return args


def main(program):
    args = parse_args(program)
    print (args)


if __name__ == "__main__":

    LOGGER.info('Authenticating...')
    credentials = get_credentials()

    resource_group_client = ResourceManagementClient(
        credentials, 
        SUBSCRIPTION_ID
    )
    network_client = NetworkManagementClient(
        credentials, 
        SUBSCRIPTION_ID
    )
    compute_client = ComputeManagementClient(
        credentials, 
        SUBSCRIPTION_ID
    )

    if resource_group_client.resource_groups.check_existence(GROUP_NAME, { 'location':LOCATION }):
        print("Resource group already exists")
    else:
        create_resource_group(resource_group_client)
        print("Resource group created")
        #input('Resource group created. Press enter to continue...')

    #deploy_vmss()

    vmss_name = "sirajsvms"
    compute_manager = VMSSComputeManager(credentials, SUBSCRIPTION_ID, GROUP_NAME, LOCATION, LOGGER)
    #compute_manager.add_or_update_vm_extension(vmss_name, "myExt")
    #compute_manager.add_null_extension(vmss_name, "MyNull2")

    #compute_manager.add_or_update_vm_extension(vmss_name, "MyBilling", VirtualMachineScaleSetExtension(publisher='Microsoft.AKS',
    #                                                                                                   type='Compute.AKS.Linux.Billing',
    #                                                                                                   type_handler_version='1.0',
    #                                                                                                   auto_upgrade_minor_version=True))

    vmss_instance = compute_manager.get_vmss_instance_view(GROUP_NAME, vmss_name)
    vmss_vm_extension = compute_manager.get_extensions_from_instance_view(vmss_instance)

    if (vmss_vm_extension is None):
        printf("No extesion found")
    else:
        for ext in vmss_vm_extension:
            print("Extension: {0}".format(ext))
