from preference_expander import PreferenceExpander


expander = PreferenceExpander()


concepts = expander.expand_preference("DSA")


print("\nORIGINAL PREFERENCE:")

print("DSA")


print("\nEXPANDED CONCEPTS:")


for index, concept in enumerate(concepts, start=1):

    print(
        f"{index}. {concept}"
    )