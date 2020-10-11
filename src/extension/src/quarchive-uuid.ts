// This module is an attempt to reproduce the proposed randomUUID function from
// https://github.com/tc39/proposal-uuid


// This is a fallback implementation intended for testing (which happens under nodejs)
function getRandomValues(arr: Uint8Array): void {
    console.warn("using fallback getRandomValues - this was only intended for testing in node");

    // Taken from MDN:
    // https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Math/random
    function getRandomIntInclusive(min, max) {
        min = Math.ceil(min);
        max = Math.floor(max);
        return Math.floor(Math.random() * (max - min + 1) + min); //The maximum is inclusive and the minimum is inclusive
    }
    for (let i = 0; i < arr.length; i++){
        arr[i] = getRandomIntInclusive(0, 255);
    }
}

var crypto;

// @ts-ignore
if (this.window) {
    crypto = window.crypto;
} else {
    crypto = {getRandomValues: getRandomValues}
}

function byteToHex(b: number): string {
    return b.toString(16).padStart(2, '0');
}

export function randomUUID(): string {
    let uuidBytes = new Uint8Array(16);

    // @ts-ignore
    crypto.getRandomValues(uuidBytes);

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
