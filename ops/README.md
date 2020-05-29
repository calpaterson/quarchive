# Ops

## Server release checklist

1. Set version number in VERSION
2. Tag
3. Push
4. Create github release, copying whl file

## Deployment

This just automates deployment.  Run with

`fab deploy $VERSION -H $HOST`
