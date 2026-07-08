import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def capacity_plot(data, path):
    figure, axis = plt.subplots(figsize=(7, 4.5))
    axis.plot(
        data["length"],
        data["baseline_success"] * 100,
        "o-",
        linewidth=2.2,
        label="Exact-match baseline",
    )
    axis.plot(
        data["length"],
        data["fham_success"] * 100,
        "s-",
        linewidth=2.2,
        label="FHAM bounded assignment (B=2)",
    )
    axis.set(
        xlabel="Secret message length (characters)",
        ylabel="Assignment success rate (%)",
        ylim=(-5, 105),
    )
    axis.grid(alpha=0.3, linestyle="--")
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=300)
    plt.close(figure)


def channel_plot(data, path):
    figure, axis = plt.subplots(figsize=(7, 4.5))
    axis.plot(data["length"], data["raw_bytes"], "o-", label="Serialized")
    axis.plot(
        data["length"], data["compressed_bytes"], "s-", label="Compressed"
    )
    axis.plot(
        data["length"], data["encrypted_bytes"], "^-", label="AES-256-GCM"
    )
    axis.set(
        xlabel="Secret message length (characters)",
        ylabel="Protected assignment-record size (bytes)",
    )
    axis.grid(alpha=0.3, linestyle="--")
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=300)
    plt.close(figure)


def bounded_plot(data, path):
    figure, axis = plt.subplots(figsize=(7, 4.5))
    for length, group in data.groupby("length"):
        axis.plot(
            group["bound"],
            group["success"] * 100,
            "o-",
            label=f"{length} characters",
        )
    axis.set(
        xlabel="Maximum allowed absolute displacement B",
        ylabel="Assignment success rate (%)",
        xscale="symlog",
        ylim=(-5, 105),
    )
    axis.grid(alpha=0.3, linestyle="--")
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=300)
    plt.close(figure)


def robustness_plot(data, path):
    figure, axis = plt.subplots(figsize=(7, 4.5))
    axis.bar(data["attack"], data["character_accuracy"] * 100)
    axis.set(
        xlabel="Transformation",
        ylabel="Mean character recovery (%)",
        ylim=(0, 105),
    )
    axis.tick_params(axis="x", rotation=30)
    axis.grid(axis="y", alpha=0.3, linestyle="--")
    figure.tight_layout()
    figure.savefig(path, dpi=300)
    plt.close(figure)
