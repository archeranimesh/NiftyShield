"""Quick verification that the access token works."""

import os
import upstox_client
from dotenv import load_dotenv

load_dotenv()


def main():
    configuration = upstox_client.Configuration()
    configuration.access_token = os.getenv("UPSTOX_ACCESS_TOKEN")

    api = upstox_client.UserApi(upstox_client.ApiClient(configuration))
    response = api.get_profile(api_version="2.0")

    print(f"Name: {response.data.user_name}")
    print(f"Email: {response.data.email}")
    print(f"Broker: {response.data.broker}")
    print(f"Exchanges: {response.data.exchanges}")
    print("\nAPI connection verified!")


if __name__ == "__main__":
    main()
