import logging

def logging_init(args) -> None:
    # silence the telemetry error spam
    for name in (
        "chromadb.telemetry",
        "chromadb.telemetry.product",
        "chromadb.telemetry.product.posthog",):
        log = logging.getLogger(name)
        log.setLevel(logging.CRITICAL)
        log.propagate = False
        log.handlers.clear()
        log.addHandler(logging.NullHandler())
    
    logging.basicConfig(
        format="[%(asctime)s][%(name)s.%(funcName)s] %(message)s",
        datefmt="%m/%d %H:%M:%S",
        level=logging.DEBUG if args.verbose else logging.INFO
    )
