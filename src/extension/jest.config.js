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
        "./quarchive-uuid.js": "<rootDir>/src/quarchive-uuid.ts"
    }
}
