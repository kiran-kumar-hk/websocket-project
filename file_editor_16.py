def save_changes(self, new_data):
    if self.single_data_row:
        return  # Do nothing, handled by save_text_data

    # Convert the edited data into a DataFrame
    edited_df = pd.DataFrame(new_data, columns=self.df.columns)

    # Check and convert boolean values to "TRUE" and "FALSE"
    for column in edited_df.columns:
        if self.df[column].dtype == bool:  # If the original column was boolean
            edited_df[column] = edited_df[column].apply(lambda x: "TRUE" if x else "FALSE")

    if self.num_headers > 0:
        headers_df = pd.DataFrame(self.non_editable_headers)
        if headers_df.shape[1] != edited_df.shape[1]:
            st.error("Mismatch between header and data columns.")
            return
        final_df = pd.concat([headers_df, self.third_header_row, edited_df], ignore_index=True)
    else:
        final_df = edited_df

    # Save the combined data back to the CSV without headers (they're already in the data)
    final_df.to_csv(self.filepath, index=False, header=False)

    # Reload the data to ensure changes are applied
    self.df = pd.read_csv(self.filepath, header=self.num_headers-1 if self.num_headers > 0 else None)
