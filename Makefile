.PHONY: demo install data test

demo: install
	python -m loop.app

install:
	python -m pip install -q -r requirements.txt

data:
	python data/generate.py

test:
	python -m pytest -q
