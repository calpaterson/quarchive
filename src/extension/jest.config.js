module.exports = {
    "roots": [
        "<rootDir>/src"
    ],
    "testMatch": [
        "<rootDir>/src/test-*.ts"
    ],
    "transform": {
        "^.+\\.(ts|tsx)$": "ts-jest"
    },
    "setupFiles": [
    ],
    "testEnvironment": "jsdom",
    "moduleNameMapper": {
        // this hack required because imports refer to js file which confuses
        // jest: https://github.com/kulshekhar/ts-jest/issues/2010
        "./quarchive-uuid.js": "<rootDir>/src/quarchive-uuid.ts",
        "./quarchive-value-objects.js": "<rootDir>/src/quarchive-value-objects.ts",
        "./quarchive-sync.js": "<rootDir>/src/quarchive-sync.ts",
        "./quarchive-config.js": "<rootDir>/src/quarchive-config.ts",
    }
}
