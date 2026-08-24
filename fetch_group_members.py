"""
Fetch all user IDs from a Roblox group in batches (paginated).

Uses the public Roblox Groups API:
    GET https://groups.roblox.com/v1/groups/{groupId}/users

No authentication is required for public group member lists.
"""

import time
import requests

GROUP_IDS = [34387869, 35997305]  # <-- replace with your Roblox group IDs
PAGE_SIZE = 100                # max allowed by the API is 100
REQUEST_DELAY = 5            # seconds between requests, to stay well under rate limits
BASE_URL = "https://groups.roblox.com/v1/groups/{group_id}/users"


def fetch_all_member_ids(group_id: int, page_size: int = 100, delay: float = 0.5) -> list[int]:
    """
    Fetch all user IDs of a Roblox group's members, one batch (page) at a time.

    Args:
        group_id: The Roblox group ID.
        page_size: Number of members to fetch per request (max 100).
        delay: Seconds to wait between requests.

    Returns:
        A list of all member user IDs.
    """
    user_ids: list[int] = []
    cursor = ""
    page_num = 1

    url = BASE_URL.format(group_id=group_id)

    while True:
        params = {
            "limit": page_size,
            "sortOrder": "Asc",
        }
        if cursor:
            params["cursor"] = cursor

        response = requests.get(url, params=params, timeout=15)

        if response.status_code == 429:
            # Rate limited - back off and retry this same page
            print("Rate limited, waiting 5s before retrying...")
            time.sleep(5)
            continue

        response.raise_for_status()
        data = response.json()

        batch_ids = [entry["user"]["userId"] for entry in data.get("data", [])]
        user_ids.extend(batch_ids)

        print(f"Batch {page_num}: fetched {len(batch_ids)} user IDs (total so far: {len(user_ids)})")

        cursor = data.get("nextPageCursor")
        if not cursor:
            break

        page_num += 1
        time.sleep(delay)

    return user_ids


def fetch_multiple_groups(group_ids: list[int], page_size: int = 100, delay: float = 0.5) -> dict[int, list[int]]:
    """
    Fetch all member user IDs for multiple Roblox groups.

    Args:
        group_ids: List of Roblox group IDs.
        page_size: Number of members to fetch per request (max 100).
        delay: Seconds to wait between requests.

    Returns:
        A dict mapping group_id -> list of member user IDs.
    """
    results: dict[int, list[int]] = {}

    for group_id in group_ids:
        print(f"\n=== Fetching group {group_id} ===")
        results[group_id] = fetch_all_member_ids(group_id, page_size=page_size, delay=delay)
        print(f"=== Group {group_id} done: {len(results[group_id])} members ===")

        # Small pause between groups too, to be polite to the API
        time.sleep(delay)

    return results


if __name__ == "__main__":
    all_results = fetch_multiple_groups(GROUP_IDS, page_size=PAGE_SIZE, delay=REQUEST_DELAY)

    grand_total = 0
    for group_id, ids in all_results.items():
        filename = f"group_{group_id}_member_ids.txt"
        with open(filename, "w") as f:
            f.write("\n".join(str(uid) for uid in ids))
        print(f"Saved {len(ids)} IDs for group {group_id} to {filename}")
        grand_total += len(ids)

    # Merge all groups' IDs into one deduplicated list
    merged_ids = set()
    for ids in all_results.values():
        merged_ids.update(ids)

    merged_sorted = sorted(merged_ids)
    with open("merged_member_ids.txt", "w") as f:
        f.write("\n".join(str(uid) for uid in merged_sorted))

    print(f"\nAll done. Total members across {len(GROUP_IDS)} groups (with duplicates): {grand_total}")
    print(f"Unique members after dedup: {len(merged_sorted)}")
    print(f"Saved merged, deduplicated list to merged_member_ids.txt")