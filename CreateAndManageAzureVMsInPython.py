import os
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
from datetime import *

#SUBSCRIPTION_ID = '490850fb-3d19-4a56-bd61-856dded531b1'
SUBSCRIPTION_ID = '5393f919-a68a-43d0-9063-4b2bda6bffdf'
OBJECT_ID = '77cabe56-880f-4cc8-af19-9458fc5cd1ec'
GROUP_NAME = 'sirajs-test'
LOCATION = 'EastUS2EUAP'
VM_NAME = 'sirajsVM'
vmss_name = "sirajsvms"



#template_filename = "template-linux.json"
template_filename = "template-linux-ext.json"
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


def deploy_vmss_extensions_only():
    cur_path = os.path.dirname(os.path.abspath(__file__))

    ext_path = os.path.join(cur_path, "extensions.json")
    with open(ext_path, "r") as ext_fh:
        ext_json = json.load(ext_fh)

    resources = ext_json['resources']
    vmss = next((res for res in resources if res['type'] == 'Microsoft.Compute/virtualMachineScaleSets'), None)
    if (vmss is None):
        print("VMSS not found")
        return
    else:
        vmss['name'] = vmss_name

        props = DeploymentProperties(template=ext_json,
                                     mode=DeploymentMode.incremental)
        poller = resource_group_client.deployments.create_or_update(GROUP_NAME, 'TestDeployment', props)
        poller.wait()

def remove_all_extensions():
    ext_profile = VirtualMachineScaleSetExtensionProfile()
    vmss_vm_profile = VirtualMachineScaleSetVMProfile(extension_profile=ext_profile)
    vmss = VirtualMachineScaleSet(location=LOCATION, virtual_machine_profile=vmss_vm_profile)
    poller = compute_client.virtual_machine_scale_sets.create_or_update(GROUP_NAME, vmss_name, vmss)
    poller.wait()


def get_dependency_map() -> dict:
    dependency_map = dict()

    # Read extensions template
    cur_path = os.path.dirname(os.path.abspath(__file__))

    ext_path = os.path.join(cur_path, "extensions.json")
    with open(ext_path, "r") as ext_fh:
        ext_json = json.load(ext_fh)

    resources = ext_json['resources']
    vmss = next((res for res in resources if res['type'] == 'Microsoft.Compute/virtualMachineScaleSets'))
    extensions = vmss['properties']['virtualMachineProfile']['extensionProfile']['extensions']

    for ext in extensions:
        ext_name = ext['name']
        dependsOn = ext['properties'].get('dependsOn')
        dependency_map[ext_name] = dependsOn

    return dependency_map

def validate_extension_sequencing(dependency_map, sorted_ext_names) -> bool:
    installed_ext = dict()

    for ext in sorted_ext_names:
        # Check if the depending extension are already installed
        if (dependency_map[ext] != None):
            for dep in dependency_map[ext]:
                if installed_ext.get(dep) is None:
                    # The dependending extension is not installed prior to the current extension
                    return False

        # Mark the current extension as installed
        installed_ext[ext] = ext
    return True 

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
    remove_all_extensions()
    deploy_vmss_extensions_only()

    compute_manager = VMSSComputeManager(credentials, SUBSCRIPTION_ID, GROUP_NAME, LOCATION, LOGGER)
    #compute_manager.add_or_update_vm_extension(vmss_name, "myExt")
    #compute_manager.add_null_extension(vmss_name, "MyNull2")

    #compute_manager.add_or_update_vm_extension(vmss_name, "MyBilling", VirtualMachineScaleSetExtension(publisher='Microsoft.AKS',
    #                                                                                                   type='Compute.AKS.Linux.Billing',
    #                                                                                                   type_handler_version='1.0',
    #                                                                                                   auto_upgrade_minor_version=True))

    #compute_manager.add_vmss_extension(GROUP_NAME, vmss_name, LOCATION)

    vmss_instance = compute_manager.get_vmss_instance_view(GROUP_NAME, vmss_name)
    vmss_vm_extensions = compute_manager.get_extensions_from_instance_view(vmss_instance)

    if (vmss_vm_extensions is None):
        print("No extesion found")
    else:
        ext_status= []
        for ext in vmss_vm_extensions:
            ext_status += [{'name': ext.name, 'status': ext.statuses[0]}]
            print("Extension {0} enabled at : {1}".format(ext.name, ext.statuses[0].time))

        sorted_ext = sorted(ext_status, key = lambda e : e['status'].time if e['status'].time != None else datetime.min.replace(tzinfo=timezone.utc))
        print("Sorted extensions: {0}".format(sorted_ext))


        sorted_extensions = sorted(vmss_vm_extensions,
                                   key = lambda ext : ext.statuses[0].time if ext.statuses[0].time != None else datetime.min.replace(tzinfo=timezone.utc))
        sorted_ext_names = [e.name for e in sorted_extensions]

    dependency_map = get_dependency_map()
    print("Dependency Map: {0}".format(dependency_map))


    result = validate_extension_sequencing(dependency_map, sorted_ext_names)

    #cur_path = os.path.dirname(os.path.abspath(__file__))
    #template_path = os.path.join(cur_path, "template-linux-ext.json")
    #with open(template_path, "r") as template_fh:
    #    template_json = json.load(template_fh)

    #ext_path = os.path.join(cur_path, "extensions.json")
    #with open(ext_path, "r") as ext_fh:
    #    ext_json = json.load(ext_fh)

    #resources = template_json['resources']
    #vmss = next((res for res in resources if res['type'] == 'Microsoft.Compute/virtualMachineScaleSets'), None)
    #if (vmss is None):
    #    print("VMSS not found")
    #else:
    #    if (vmss.get('properties') is None):
    #        vmss['properties'] = {}

    #    if (vmss['properties'].get('virtualMachineProfile') is None):
    #        vmss['properties']['virtualMachineProfile'] = {}

    #    vmss['properties']['virtualMachineProfile']['extensionProfile'] = ext_json
