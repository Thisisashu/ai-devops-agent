from agent.agent import DevOpsAgent


def main():

    print("=" * 50)
    print("          AI DEVOPS AGENT")
    print("=" * 50)

    print("Type 'exit' to quit.")
    print()

    agent = DevOpsAgent()

    while True:

        user_input = input("You: ")

        if user_input.lower() in [
            "exit",
            "quit"
        ]:

            print("Goodbye!")

            break

        if not user_input:

            continue

        try:

            response = agent.run(
                user_input
            )

            print()
            print("Agent:", response)
            print()

        except Exception as e:

            print()
            print("ERROR:", e)
            print()


if __name__ == "__main__":

    main()
