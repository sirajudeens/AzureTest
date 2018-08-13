
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.compute import *
from azure.mgmt.compute.models import *

from msrestazure.azure_exceptions import CloudError

from time import sleep

class ComputeManager(object):

    def __init__(self,
                 credentials,
                 sub_id: str,
                 rg_name: str,
                 location: str,
                 logger):
        if rg_name is None or rg_name.isspace():
            raise ValueError('rg name cannot be None or empty/whitespace')
        if location is None or location.isspace():
            raise ValueError('location cannot be None or empty/whitespace')

        self.credentials = credentials
        self.sub_id = sub_id
        self.rg_name = rg_name
        self.location = location
        self._logger = logger
        self._compute_client = None

    @property
    def compute_client(self) -> ComputeManagementClient:
        if self._compute_client is None:
            self._compute_client = ComputeManagementClient(self.credentials, self.sub_id)
        return self._compute_client


class VMSSComputeManager(ComputeManager):
    def __init__(self,
                 credentials,
                 sub_id: str,
                 rg_name: str,
                 location: str,
                 logger):
        super(VMSSComputeManager, self).__init__(credentials, sub_id, rg_name, location, logger)
        self.create_or_update_extensions = self.compute_client.virtual_machine_scale_set_extensions.create_or_update
        self.delete_extensions = self.compute_client.virtual_machine_scale_set_extensions.delete

    def get_vmss_instance_view(self, rgn, vmn):
        return self.compute_client.virtual_machine_scale_sets.get(rgn, vmn)

    def get_vmss_vms(self, vmss_name):
        return self.compute_client.virtual_machine_scale_set_vms.list(self.rg_name,
                                                                      vmss_name,
                                                                      expand="instanceView")

    def get_extensions_from_instance_view(self, instance_view):
        for vm in self.get_vmss_vms(instance_view.name):
            return vm.instance_view.extensions
        return None

    def generate_default_ext(self) -> VirtualMachineExtension:
        settings = {'commandToExecute': "echo \'Hello World!\'"}

        return VirtualMachineExtension(
            location=self.location,
            publisher='Microsoft.Azure.Extensions',
            virtual_machine_extension_type='CustomScript',
            type_handler_version='2.0',
            auto_upgrade_minor_version=True,
            settings=settings
        )

    def add_vmss_extension(self,
                           rg_name: str,
                           vmss_name: str,
                           location: str):
        extensions = []
        #extensions.append(VirtualMachineScaleSetExtension(
        #    name='MyNull_from_python',
        #    publisher='Microsoft.OSTCExtensions',
        #    type='Null',
        #    type_handler_version='1.3'))

        ext_profile = VirtualMachineScaleSetExtensionProfile(extensions)
        vmprofile = VirtualMachineScaleSetVMProfile(extension_profile=ext_profile)
        vmss = VirtualMachineScaleSet(location=location, virtual_machine_profile=vmprofile)
        poller = self.compute_client.virtual_machine_scale_sets.create_or_update(rg_name, vmss_name, vmss)
        poller.wait()
        return

    def add_or_update_vm_extension(self, 
                                   vmss_name: str,
                                   ext_name: str,
                                   ext_properties: VirtualMachineExtension = None):

        if vmss_name is None or vmss_name.isspace():
            raise ValueError('vm name cannot be None or empty/whitespace')
        if ext_name is None or ext_name.isspace():
            raise ValueError('ext name cannot be None or empty/whitespace')

        if ext_properties is None:
            ext_properties = self.generate_default_ext()

        self._logger.info("Add/update extension [%s, %s]...", ext_name, vmss_name)
        max_retries = 3
        retries = max_retries
        result = False
        while result is False and retries > 0:
            try:
                # type: AzureOperationPoller
                poller = self.compute_client.virtual_machine_scale_set_extensions.create_or_update(self.rg_name,
                                                                                                   vmss_name,
                                                                                                   ext_name,
                                                                                                   ext_properties)
                poller.wait()
                self._logger.debug("...extension is added/updated")
                result = True
            except CloudError as ce:
                self._logger.debug("Extension deployment error: "
                                   "[{0}], [{1}], [{2}], [{3}], [{4}]".format(ce.error,
                                                                              ce.message,
                                                                              ce.status_code,
                                                                              ce.inner_exception,
                                                                              ce.response))
                self._logger.error("Extension deployment error: {0}".format(ce))

                if 'NonTransientError' in str(ce.error) or retries <= 0:
                    self._logger.error("...giving up [{0}]".format(ce.message))
                else:
                    self._logger.info("...retrying [{0} attempts remaining]".format(retries))
                    retries -= 1
                    self.process_create_or_update_error(ce)
                    sleep(30 * (max_retries - retries))
        return result

    def create_vmss_extension_properties(self,
                                         publisher,
                                         type,
                                         version,
                                         settings=None,
                                         protected_settings=None,
                                         force_update_tag=None,
                                         auto_upgrade_minor_version=True) -> VirtualMachineScaleSetExtension:
        return VirtualMachineScaleSetExtension(
            publisher=publisher,
            type=type,
            type_handler_version=version,
            auto_upgrade_minor_version=auto_upgrade_minor_version,
            settings=settings,
            protected_settings=protected_settings,
            force_update_tag=force_update_tag
        )

    def add_null_extension(self,
                           vmss_name: str,
                           ext_name: str):
        extension_properties = self.create_vmss_extension_properties(publisher='Microsoft.OSTCExtensions',
                                                                     type='Null',
                                                                     version='1.3',
                                                                     settings={},
                                                                     auto_upgrade_minor_version=True)
        self.add_or_update_vm_extension(vmss_name, ext_name, extension_properties)