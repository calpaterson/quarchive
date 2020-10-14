module.exports = {
    "roots": [
        "<rootDir>/src"
    ],
    "testMatch": [
        "**/__tests__/**/*.+(ts|tsx|js)",
        "**/?(*.)+(spec|test).+(ts|tsx|js)"
    ],
    "transform": {
        "^.+\\.(ts|tsx)$": "ts-jest"
    },
    "setupFiles": [
    ],
    "testEnvironment": "jsdom",
    "moduleNameMapper": {
        "./quarchive-uuid.js": "<rootDir>/src/quarchive-uuid.ts"
    }
}
