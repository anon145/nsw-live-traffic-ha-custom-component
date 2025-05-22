# This script is for directly testing the TfNSW Live Traffic API endpoints.
# Replace 'YOUR_API_KEY_HERE' with your actual API key before running.

import asyncio
import aiohttp
import json

# --- Configuration ---
# PASTE YOUR ACTUAL API KEY HERE:
API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiI3MTdQWU9YWUQ0TW5vN0pzYVNyOTFtY09NRXRYS25JeXVjd3RoMHd2X0t3IiwiaWF0IjoxNzQ3NzM1MDk2fQ.hv2SEhhQxbY1SaBlz4Wujso-XZzGKlrqb1BvesabBSI"

# Choose one of the endpoints that is currently failing with a 400 error:
#ENDPOINT_URL = "https://api.transport.nsw.gov.au/v1/live/hazards/roadwork/open"
#ENDPOINT_URL = "https://api.transport.nsw.gov.au/v1/live/hazards/fire/open"
#ENDPOINT_URL = "https://api.transport.nsw.gov.au/v1/live/hazards/flood/open"
#ENDPOINT_URL = "https://api.transport.nsw.gov.au/v1/live/hazards/majorevent/open" # Example, change as needed
ENDPOINT_URL = "https://api.transport.nsw.gov.au/v1/live/hazards/alpine/open"

HEADERS = {
    "Authorization": f"apikey {API_KEY}",
    "Accept": "application/json",
    # Add any other headers here if we need to test them, e.g.:
    # "Content-Type": "application/json", # Generally not needed for GET
}

async def test_api_call():
    print(f"Testing endpoint: {ENDPOINT_URL}")
    print(f"Using API Key: {API_KEY[:4]}...{API_KEY[-4:] if len(API_KEY) > 8 else ''}") # Print partial key for confirmation
    print(f"Using Headers: {HEADERS}")

    if API_KEY == "YOUR_API_KEY_HERE":
        print("\n--------------------------------------------------------------------")
        print("!!! ERROR: Please replace 'YOUR_API_KEY_HERE' with your actual API key in the script. !!!")
        print("--------------------------------------------------------------------\n")
        return

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(ENDPOINT_URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as response:
                print(f"\n--- Response ---")
                print(f"Status Code: {response.status}")
                print(f"Response Headers:")
                for key, value in response.headers.items():
                    print(f"  {key}: {value}")
                
                response_text = await response.text()
                print(f"Response Body (text):")
                print(response_text)

                # Try to parse as JSON if content type suggests it
                content_type_lower = response.headers.get("Content-Type", "").lower()
                if "application/json" in content_type_lower or \
                   "application/geo+json" in content_type_lower:
                    try:
                        response_json = json.loads(response_text)
                        print(f"Response Body (parsed as JSON):")
                        print(json.dumps(response_json, indent=2))
                    except json.JSONDecodeError as e:
                        print(f"Could not parse response body as JSON: {e}")

        except aiohttp.ClientResponseError as e:
            print(f"\n--- ClientResponseError ---")
            print(f"Status: {e.status}")
            print(f"Message: {e.message}")
            print(f"Headers: {e.headers}")
            # The string representation of ClientResponseError often contains the body or more details
            print(f"Error Details: {e}")
        except aiohttp.ClientError as e:
            print(f"\n--- ClientError (e.g., connection issue) ---")
            print(f"Error: {e}")
        except asyncio.TimeoutError:
            print(f"\n--- TimeoutError ---")
            print(f"The request to {ENDPOINT_URL} timed out.")
        except Exception as e:
            print(f"\n--- An unexpected error occurred ---")
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_api_call()) 