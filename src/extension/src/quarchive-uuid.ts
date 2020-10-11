// // This module is an attempt to reproduce the proposed randomUUID function from
// // https://github.com/tc39/proposal-uuid

function byteToHex(b: number): string {
    return b.toString(16).padStart(2, '0');
}

export function randomUUID(): string {
    let uuidBytes = new Uint8Array(16);

    window.crypto.getRandomValues(uuidBytes);

    // Set the version and the variant
    uuidBytes[6] = (uuidBytes[6] & 0x0f) | 0x40;
    uuidBytes[8] = (uuidBytes[8] & 0xbf) | 0x80;

    let uuidHex = (Array.from(uuidBytes)).map(byteToHex);

    let characters = [
        ...uuidHex.slice(0, 4),
        '-',
        ...uuidHex.slice(4, 6),
        '-',
        ...uuidHex.slice(6, 8),
        '-',
        ...uuidHex.slice(8, 10),
        '-',
        ...uuidHex.slice(10, 16),
    ];

    return characters.join('');
}
