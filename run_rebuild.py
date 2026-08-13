import urllib.request
import json
import os

# We will just write a small script that opens the old version from git, modifies it using python replace rules, and writes it back.
# Wait, I don't need urllib. I'll just write code string in chunks to avoid ENAMETOOLONG
