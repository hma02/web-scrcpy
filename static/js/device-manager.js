/**
 * DeviceManager - Handles device detection, selection, and page routing
 * Provides utilities for managing multiple devices and switching between stream modes
 */

class DeviceManager {
    constructor(options = {}) {
        this.devices = [];
        this.selectedDevices = [];
        this.pollInterval = options.pollInterval || 5000;
        this.maxDevices = options.maxDevices || 2;
        this.baseUrl = options.baseUrl || '/api';
        this.onDevicesChanged = options.onDevicesChanged || null;
        this.pollingActive = false;
        this.lastKnownDevices = [];
    }

    /**
     * Start polling for device changes
     */
    startPolling() {
        if (this.pollingActive) return;
        this.pollingActive = true;
        this._poll();
    }

    /**
     * Stop polling for device changes
     */
    stopPolling() {
        this.pollingActive = false;
    }

    /**
     * Internal polling function
     */
    _poll = () => {
        if (!this.pollingActive) return;

        this.fetchDevices()
            .then(() => {
                setTimeout(this._poll, this.pollInterval);
            })
            .catch(err => {
                console.error('Error fetching devices:', err);
                setTimeout(this._poll, this.pollInterval);
            });
    }

    /**
     * Fetch connected devices from server
     */
    async fetchDevices() {
        try {
            const response = await fetch(`${this.baseUrl}/devices`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            const newDevices = Array.isArray(data) ? data : (data.devices || []);

            // Check if devices changed
            if (this._devicesChanged(newDevices)) {
                this.devices = newDevices;
                if (this.onDevicesChanged) {
                    this.onDevicesChanged(this.devices);
                }
            }

            return this.devices;
        } catch (error) {
            console.error('Failed to fetch devices:', error);
            throw error;
        }
    }

    /**
     * Check if device list has changed
     */
    _devicesChanged(newDevices) {
        if (this.lastKnownDevices.length !== newDevices.length) {
            this.lastKnownDevices = [...newDevices];
            return true;
        }

        for (let i = 0; i < newDevices.length; i++) {
            if (this.lastKnownDevices[i] !== newDevices[i]) {
                this.lastKnownDevices = [...newDevices];
                return true;
            }
        }

        return false;
    }

    /**
     * Get current device count
     */
    getDeviceCount() {
        return this.devices.length;
    }

    /**
     * Get all devices
     */
    getAllDevices() {
        return [...this.devices];
    }

    /**
     * Get a specific device by UDID
     */
    getDevice(udid) {
        return this.devices.find(d => d === udid || (typeof d === 'object' && d.udid === udid));
    }

    /**
     * Select a device
     */
    selectDevice(udid) {
        if (!this.selectedDevices.includes(udid) && this.selectedDevices.length < this.maxDevices) {
            this.selectedDevices.push(udid);
            return true;
        }
        return false;
    }

    /**
     * Deselect a device
     */
    deselectDevice(udid) {
        const index = this.selectedDevices.indexOf(udid);
        if (index > -1) {
            this.selectedDevices.splice(index, 1);
            return true;
        }
        return false;
    }

    /**
     * Get selected devices
     */
    getSelectedDevices() {
        return [...this.selectedDevices];
    }

    /**
     * Clear selection
     */
    clearSelection() {
        this.selectedDevices = [];
    }

    /**
     * Determine which view to render based on connected devices
     */
    determineView() {
        const count = this.getDeviceCount();
        if (count === 0) {
            return 'no-devices';
        } else if (count === 1) {
            return 'single-device';
        } else {
            return 'multiple-devices';
        }
    }

    /**
     * Get route for streaming
     */
    getStreamRoute(deviceUdids = null) {
        if (!deviceUdids) {
            deviceUdids = this.selectedDevices;
        }

        if (deviceUdids.length === 0) {
            return '/';
        } else if (deviceUdids.length === 1) {
            return `/stream-single?device=${encodeURIComponent(deviceUdids[0])}`;
        } else if (deviceUdids.length === 2) {
            return `/stream-dual?device1=${encodeURIComponent(deviceUdids[0])}&device2=${encodeURIComponent(deviceUdids[1])}`;
        } else {
            // For more than 2 devices, just use the first 2
            return `/stream-dual?device1=${encodeURIComponent(deviceUdids[0])}&device2=${encodeURIComponent(deviceUdids[1])}`;
        }
    }

    /**
     * Navigate to stream page
     */
    navigateToStream(deviceUdids = null) {
        const route = this.getStreamRoute(deviceUdids);
        window.location.href = route;
    }

    /**
     * Get formatted device name
     */
    formatDeviceName(udid) {
        if (typeof udid === 'object' && udid.name) {
            return udid.name;
        }
        // Extract model from UDID if possible or return truncated UDID
        if (udid && udid.length > 20) {
            return udid.substring(0, 20) + '...';
        }
        return udid || 'Unknown Device';
    }

    /**
     * Check if device selection is valid for streaming
     */
    isValidSelection(deviceUdids = null) {
        const toCheck = deviceUdids || this.selectedDevices;
        return toCheck.length > 0 && toCheck.length <= this.maxDevices;
    }

    /**
     * Export selection for URL parameter
     */
    exportSelection() {
        return {
            devices: this.selectedDevices,
            count: this.selectedDevices.length,
            route: this.getStreamRoute()
        };
    }

    /**
     * Get detailed status information
     */
    getStatus() {
        return {
            totalDevices: this.devices.length,
            selectedDevices: this.selectedDevices.length,
            devices: this.devices,
            selected: this.selectedDevices,
            view: this.determineView(),
            pollingActive: this.pollingActive
        };
    }

    /**
     * Destroy the manager and clean up
     */
    destroy() {
        this.stopPolling();
        this.clearSelection();
        this.devices = [];
        this.lastKnownDevices = [];
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { DeviceManager };
}
