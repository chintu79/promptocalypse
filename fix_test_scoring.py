import re

with open("backend/tests/test_scoring.py", "r") as f:
    content = f.read()

# Fix verify_and_progress(db, user, key) -> verify_and_progress(db, user, level, key)
# test_unknown_user_returns_not_found
content = content.replace('verify_and_progress(db, "usr_ghost", "FLAG{alpha_912}")', 'verify_and_progress(db, "usr_ghost", 1, "FLAG{alpha_912}")')
content = content.replace('verify_and_progress(db, "usr_score_1", LEVEL_KEYS[1])', 'verify_and_progress(db, "usr_score_1", 1, LEVEL_KEYS[1])')
content = content.replace('verify_and_progress(db, "usr_score_1", "FLAG{wrong}")', 'verify_and_progress(db, "usr_score_1", 2, "FLAG{wrong}")')
content = content.replace('verify_and_progress(\n                db, "usr_score_1", f"  {LEVEL_KEYS[1]}\\n"\n            )', 'verify_and_progress(\n                db, "usr_score_1", 1, f"  {LEVEL_KEYS[1]}\\n"\n            )')
content = content.replace('verify_and_progress(db, "usr_score_1", LEVEL_KEYS[2])', 'verify_and_progress(db, "usr_score_1", 2, LEVEL_KEYS[2])')
content = content.replace('verify_and_progress(db, "usr_score_1", LEVEL_KEYS[3])', 'verify_and_progress(db, "usr_score_1", 3, LEVEL_KEYS[3])')
content = content.replace('verify_and_progress(db, "usr_score_1", "nope")', 'verify_and_progress(db, "usr_score_1", 1, "nope")')
content = content.replace('verify_and_progress(db, "usr_score_1", "still nope")', 'verify_and_progress(db, "usr_score_1", 1, "still nope")')
content = content.replace('verify_and_progress(\n                    db, f"usr_par_{idx}", LEVEL_KEYS[1]\n                )', 'verify_and_progress(\n                    db, f"usr_par_{idx}", 1, LEVEL_KEYS[1]\n                )')

# Fix calculate_final_score args
content = content.replace('calculate_final_score(5, 10, 0)', 'calculate_final_score(3, 5, 10, 0)')
content = content.replace('calculate_final_score(4, 1, 0)', 'calculate_final_score(3, 4, 1, 0)')
content = content.replace('calculate_final_score(1, 0, 0)', 'calculate_final_score(3, 1, 0, 0)')
content = content.replace('calculate_final_score(3, 0, 0)', 'calculate_final_score(3, 3, 0, 0)')
content = content.replace('calculate_final_score(3, 10000, 0)', 'calculate_final_score(3, 3, 10000, 0)')
content = content.replace('calculate_final_score(1, 0, 1)', 'calculate_final_score(3, 1, 0, 1)')
content = content.replace('calculate_final_score(6, 12, 2)', 'calculate_final_score(3, 6, 12, 2)')

# Fix TestSubmitKeyEndpoint
content = content.replace('{"user_id": "usr_ghost", "key": LEVEL_KEYS[1]}', '{"user_id": "usr_ghost", "level": 1, "key": LEVEL_KEYS[1]}')
content = content.replace('{"user_id": "usr_l1", "key": "FLAG{nope}"}', '{"user_id": "usr_l1", "level": 1, "key": "FLAG{nope}"}')
content = content.replace('{"user_id": "usr_l1", "key": LEVEL_KEYS[1]}', '{"user_id": "usr_l1", "level": 1, "key": LEVEL_KEYS[1]}')
content = content.replace('{"user_id": "usr_l3", "key": LEVEL_KEYS[3]}', '{"user_id": "usr_l3", "level": 3, "key": LEVEL_KEYS[3]}')
content = content.replace('{"user_id": "usr_done", "key": LEVEL_KEYS[1]}', '{"user_id": "usr_done", "level": 1, "key": LEVEL_KEYS[1]}')

with open("backend/tests/test_scoring.py", "w") as f:
    f.write(content)
