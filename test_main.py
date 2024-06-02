import pytest
import main


def test_offers_that_match_criteria():
    chat_ids = main.get_value_from_config(["chats"]).keys()

    empty_dict_from_connection_error = {}
    for chat_id in chat_ids:
        matching_offers = main.offers_that_match_criteria(empty_dict_from_connection_error, chat_id, check_if_known=False)

    assert True


def test_main():
    main.main()