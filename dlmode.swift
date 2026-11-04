// SPDX-License-Identifier: MIT
// Ask a running FM-1 firmware to restart into the chip's download mode, with the SysEx
// F0 22 24 35 7D F7 (the same as M-Flasher's DOWNLOAD MODE button). It goes to the first MIDI
// port whose name has "FM-1" in it (M-VAVE's firmware, a renamed build) or starts "Felucca..." (Felucca-family firmware).
// fm1_recover.py runs it by itself; exits 1 when no such port is connected.
import CoreMIDI
import Foundation

var client = MIDIClientRef(), port = MIDIPortRef()
MIDIClientCreate("fm1" as CFString, nil, nil, &client)
MIDIOutputPortCreate(client, "out" as CFString, &port)
for i in 0..<MIDIGetNumberOfDestinations() {
    let dest = MIDIGetDestination(i)
    var name: Unmanaged<CFString>?
    MIDIObjectGetStringProperty(dest, kMIDIPropertyDisplayName, &name)
    let s = name?.takeRetainedValue() as String? ?? ""
    guard s.hasPrefix("Felucca") || s.contains("FM-1") else { continue }   // (also a renamed one, "My FM-1")
    var bytes: [UInt8] = [0xF0, 0x22, 0x24, 0x35, 0x7D, 0xF7]
    var list = MIDIPacketList()
    _ = MIDIPacketListAdd(&list, MemoryLayout<MIDIPacketList>.size, MIDIPacketListInit(&list), 0, bytes.count, &bytes)
    MIDISend(port, dest, &list)
    print("Sent        download-mode request to \(s)")
    Thread.sleep(forTimeInterval: 0.5)
    exit(0)
}
exit(1)
