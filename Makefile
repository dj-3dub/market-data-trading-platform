.PHONY: doctor-vm

# Run the VM Doctor script
doctor-vm:
	@echo "Running VM Doctor..."
	@bash tools/vm-doctor/vm_doctor.sh

