import pytest
from src.game import Card, Deck


def test_card_str_and_eq():
    c1 = Card('rojo', '5')
    assert str(c1) == 'ROJO 5'
    c2 = Card('ROJO', '5')
    assert c1 == c2
    with pytest.raises(ValueError):
        Card('negro', '5')  # color inválido
    with pytest.raises(ValueError):
        Card('rojo', '10')  # valor inválido


def test_deck_initial_count():
    deck = Deck()
    assert deck.count() == 40


def test_deck_shuffle_and_draw():
    deck = Deck()
    before = deck.cards.copy()
    deck.shuffle()
    # Después de barajar, el orden debería cambiar
    assert deck.cards != before
    drawn = deck.draw(5)
    assert len(drawn) == 5
    assert deck.count() == 35


def test_draw_more_than_available():
    deck = Deck()
    deck.reset()
    cards = deck.draw(100)
    assert len(cards) == 40
    assert deck.count() == 0


def test_draw_invalid_number():
    deck = Deck()
    with pytest.raises(ValueError):
        deck.draw(0)